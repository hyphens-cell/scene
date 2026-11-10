"""One STA command loop per Office engine, isolated from the Qt event loop.

The process main thread is explicitly initialized as STA. COM proxies never leave
that thread: the pipe transports only dataclasses, numbers, strings and RGB bytes.
Only our Python helper may be terminated on timeout, never a user's Office process.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import time
from collections import deque
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Signal

from pdf_presenter.i18n import tr

log = logging.getLogger(__name__)


def _execute_with_retry(session, document_id, method, arguments):
    import pythoncom

    deadline = time.monotonic() + 2
    while True:
        try:
            return session.execute(document_id, method, arguments)
        except Exception as exc:
            # These two HRESULTs mean Office rejected the call before executing
            # it. Retry only these transient busy states, never arbitrary errors.
            if (
                getattr(exc, "hresult", None) not in (-2147418111, -2147417846)
                or time.monotonic() >= deadline
            ):
                raise
            pythoncom.PumpWaitingMessages()
            time.sleep(0.05)


def _sta_loop(pipe, engine: str) -> None:
    import ctypes

    import pythoncom

    # The spawned helper has no QApplication. Match Qt's per-monitor coordinates
    # before creating Office windows so Win32 does not virtualize mixed-DPI rects.
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    session = None
    try:
        if engine == "powerpoint":
            from .powerpoint_session import PowerPointSession

            session = PowerPointSession()
        else:
            from .libreoffice_session import LibreOfficeSession

            session = LibreOfficeSession()
        while True:
            pythoncom.PumpWaitingMessages()
            if not pipe.poll(0.03):
                continue
            request = pipe.recv()
            if request is None:
                break
            request_id, document_id, method, arguments = request
            try:
                result = _execute_with_retry(session, document_id, method, arguments)
                pipe.send((request_id, True, result))
            except Exception as exc:
                log.exception("Office command failed: %s/%s", engine, method)
                pipe.send((request_id, False, str(exc)))
    except (EOFError, BrokenPipeError, OSError):
        pass
    except Exception as exc:
        try:
            pipe.send(("startup", False, str(exc)))
        except (OSError, EOFError):
            pass
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                log.exception("Office cleanup failed")
        session = None
        pythoncom.CoUninitialize()
        pipe.close()


@dataclass
class Command:
    id: str
    document_id: str
    method: str
    arguments: dict
    priority: int
    timeout: float


class OfficeService(QObject):
    completed = Signal(str, str, object)
    failed = Signal(str, str, str)
    disconnected = Signal(str)
    closed = Signal()

    def __init__(self, engine: str, parent=None) -> None:
        super().__init__(parent)
        self.engine = engine
        self._process: Any = None
        self._pipe = None
        self._queue: deque[Command] = deque()
        self._busy: Command | None = None
        self._since = 0.0
        self._closing = False
        self._close_since = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    @property
    def idle(self) -> bool:
        return self._busy is None and not self._queue

    def _launch(self) -> None:
        context = mp.get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(target=_sta_loop, args=(child, self.engine), daemon=True)
        try:
            process.start()
        except Exception:
            parent.close()
            child.close()
            raise
        child.close()
        self._pipe, self._process = parent, process

    def call(
        self,
        document_id: str,
        method: str,
        arguments: dict | None = None,
        *,
        priority: int = 0,
        timeout: float = 15,
    ) -> str:
        if self._closing:
            raise RuntimeError(tr("Движок закрывается."))
        if self._process is None:
            self._launch()
        command = Command(uuid4().hex, document_id, method, arguments or {}, priority, timeout)
        self._queue.append(command)
        return command.id

    def cancel_methods(self, document_id: str, methods: set[str] | None = None) -> set[str]:
        removed = {
            command.id
            for command in self._queue
            if command.document_id == document_id and (methods is None or command.method in methods)
        }
        self._queue = deque(command for command in self._queue if command.id not in removed)
        return removed

    def cancel_previews(self, document_id: str) -> set[str]:
        return self.cancel_methods(document_id, {"preview"})

    def cancel_document(self, document_id: str) -> None:
        self.cancel_methods(document_id)

    def _poll(self) -> None:
        if self._process is None:
            return
        if self._closing:
            # A large preview may still be in flight. Drain its pipe so the STA
            # worker can finish send(), receive shutdown and release COM objects.
            try:
                if self._pipe.poll():
                    self._pipe.recv()
            except (OSError, EOFError):
                pass
            if not self._process.is_alive():
                self._release()
                self.closed.emit()
            elif time.monotonic() - self._close_since > 8:
                self._abort(
                    tr(
                        "Внешний движок не завершил освобождение ресурсов за 8 секунд. Чужие процессы Office не закрывались."
                    )
                )
                self.closed.emit()
            return
        try:
            if self._pipe.poll():
                request_id, success, result = self._pipe.recv()
                if request_id == "startup":
                    raise RuntimeError(
                        tr("Не удалось запустить {p0}: {p1}", p0=self.engine, p1=result)
                    )
                command = self._busy
                self._busy = None
                if command and request_id == command.id:
                    if success:
                        self.completed.emit(command.document_id, command.id, result)
                    else:
                        self.failed.emit(command.document_id, command.id, result)
            if not self._process.is_alive():
                raise RuntimeError(
                    tr("Управляющий процесс Office завершился. Откройте презентацию повторно.")
                )
            if self._busy and time.monotonic() - self._since > self._busy.timeout:
                raise RuntimeError(
                    tr(
                        "{p0} не отвечает на команду {p1}. Возможен запрос пароля или диалог Office. Проверьте PowerPoint/LibreOffice и откройте файл повторно. Другие процессы Office не завершались.",
                        p0=self.engine,
                        p1=self._busy.method,
                    )
                )
            if self._busy is None and self._queue:
                command = min(self._queue, key=lambda item: item.priority)
                self._queue.remove(command)
                self._pipe.send(
                    (command.id, command.document_id, command.method, command.arguments)
                )
                self._busy, self._since = command, time.monotonic()
        except (OSError, EOFError, RuntimeError) as exc:
            self._abort(str(exc))

    def _release(self) -> None:
        if self._process is not None:
            self._process.join(timeout=0.05)
            if not self._process.is_alive():
                self._process.close()
        if self._pipe is not None:
            self._pipe.close()
        self._process = self._pipe = None
        self._busy = None
        self._queue.clear()

    def _abort(self, message: str) -> None:
        log.error(message)
        if self._process and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=0.2)
        self._release()
        self.disconnected.emit(message)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._queue.clear()
        self._close_since = time.monotonic()
        if self._pipe is None:
            self.closed.emit()
        else:
            try:
                self._pipe.send(None)
            except OSError:
                self._release()
                self.closed.emit()

    def force_close(self) -> None:
        """Final application shutdown fallback; only terminates our helper."""
        self._timer.stop()
        if self._process:
            self._abort(tr("Управляющий процесс завершён при закрытии Сцена."))


class OfficeServicePool:
    def __init__(self) -> None:
        self.services: dict[str, OfficeService] = {}

    def get(self, engine: str) -> OfficeService:
        service = self.services.get(engine)
        if service is None or service._closing:
            service = OfficeService(engine)
            self.services[engine] = service
        return service

    def close(self) -> None:
        for service in self.services.values():
            service.close()

    @property
    def finished(self) -> bool:
        return all(service._process is None for service in self.services.values())

    def force_close(self) -> None:
        for service in self.services.values():
            service.force_close()
