"""Nonblocking Qt IPC for an isolated, owned browser process."""

import multiprocessing as mp
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from pdf_presenter.i18n import tr

from .canva_worker import run_canva_worker


class CanvaService(QObject):
    received = Signal(str, object)

    def __init__(self, source):
        super().__init__(QApplication.instance())
        from .webview_runtime import require_webview2

        require_webview2()
        self.closing = False
        self.since = time.monotonic()
        self.job = None
        self.process = None
        self.pipe = None
        self.pending = 0
        self.initialized = False
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._poll)
        context = mp.get_context("spawn")
        self.pipe, child = context.Pipe()
        try:
            import win32api
            import win32job

            self.job = win32job.CreateJobObject(None, "")
            limits = win32job.QueryInformationJobObject(
                self.job, win32job.JobObjectExtendedLimitInformation
            )
            limits["BasicLimitInformation"]["LimitFlags"] = (
                win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            )
            win32job.SetInformationJobObject(
                self.job, win32job.JobObjectExtendedLimitInformation, limits
            )
            self.process = context.Process(target=run_canva_worker, args=(child,), daemon=True)
            self.process.start()
            handle = win32api.OpenProcess(0x100 | 0x1, False, self.process.pid)
            try:
                win32job.AssignProcessToJobObject(self.job, handle)
            finally:
                handle.Close()
            child.close()
            self.pipe.send(source)
            self.timer.start()
        except Exception:
            child.close()
            if self.process and self.process.is_alive():
                self.process.terminate()
            self._release()
            raise

    def send(self, method, **values):
        if self.closing:
            return
        if self.pending == 0:
            self.since = time.monotonic()
        self.pending += 1
        try:
            self.pipe.send((method, values))
        except (OSError, EOFError):
            self.close(force=True)
            self.received.emit("error", tr("Соединение с Canva закрыто."))

    def _poll(self):
        if self.closing:
            if not self.process.is_alive() or time.monotonic() - self.since > 4:
                self._release()
            return
        try:
            while self.pipe.poll():
                method, result = self.pipe.recv()
                if method == "loaded":
                    self.initialized = True
                self.pending = max(0, self.pending - 1)
                self.since = time.monotonic()
                self.received.emit(method, result)
                if self.closing:
                    return
            if not self.process.is_alive():
                raise RuntimeError(tr("Окно Canva закрыто. Откройте материал повторно."))
            if (self.pending or not self.initialized) and time.monotonic() - self.since > (
                15 if self.pending else 80
            ):
                raise RuntimeError(tr("Canva не отвечает. Проверьте подключение к интернету."))
        except (OSError, EOFError, RuntimeError) as exc:
            self.close(force=True)
            self.received.emit("error", str(exc))

    def close(self, *, force=False):
        if self.closing:
            return
        self.closing = True
        if force:
            self._release()
            return
        self.since = time.monotonic()
        try:
            self.pipe.send(None)
        except (OSError, EOFError):
            pass

    def _release(self):
        self.timer.stop()
        if self.job:
            self.job.Close()  # Kills only our helper and its WebView2 descendants.
            self.job = None
        if self.process:
            self.process.join(0.1)
        if self.pipe:
            self.pipe.close()
        self.deleteLater()
