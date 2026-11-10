from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer, Signal

from pdf_presenter.i18n import tr


class DisplayHandoffCoordinator(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, audience, parent=None) -> None:
        super().__init__(parent)
        self.audience = audience
        self.previous = self.candidate = None
        self.index = 0
        self.target = None
        self.busy = False
        self._connections = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(25000)
        self._timer.timeout.connect(
            lambda: self._fail(
                tr(
                    "Передача экрана превысила допустимое время. На аудитории сохранён защитный экран."
                )
            )
        )

    def switch(self, previous, candidate, index, target) -> None:
        if self.busy:
            raise RuntimeError(tr("Дождитесь передачи экрана или остановите показ."))
        self.previous, self.candidate = previous, candidate
        self.index, self.target = index, target
        self.busy = True
        self.audience.hold()
        self._timer.start()
        self._connect(candidate.started, self._ready)
        self._connect(candidate.failed, self._fail)
        if previous is not None and previous.active:
            self._connect(previous.stopped, self._start_candidate)
            if previous is not candidate:
                self._connect(previous.failed, self._fail)
            try:
                previous.stop()
            except Exception as exc:
                self._fail(str(exc))
        else:
            self._start_candidate()

    def _connect(self, signal, callback) -> None:
        signal.connect(callback)
        self._connections.append((signal, callback))

    def _disconnect(self) -> None:
        for signal, callback in self._connections:
            try:
                signal.disconnect(callback)
            except (RuntimeError, TypeError):
                pass
        self._connections.clear()
        self._timer.stop()

    def _start_candidate(self) -> None:
        if not self.busy:
            return
        try:
            self.candidate.set_display_target(self.target)
            self.candidate.start(self.index)
        except Exception as exc:
            self._fail(str(exc))

    def _ready(self) -> None:
        if not self.busy:
            return
        backend = self.candidate
        self.busy = False
        self._disconnect()
        # Presenter commits its new document/preview before the cover is released.
        self.completed.emit(backend)
        self.audience.attach(backend)
        self.previous = self.candidate = None

    def _fail(self, message: str) -> None:
        if not self.busy:
            return
        self.busy = False
        self._disconnect()
        if self.candidate is not None:
            try:
                self.candidate.stop()
            except Exception:
                logging.getLogger(__name__).exception("Candidate cleanup failed during handoff")
        self.audience.handoff = False
        self.audience.apply_mode("black")
        self.failed.emit(message)
        self.previous = self.candidate = None

    def cancel(self) -> None:
        self.busy = False
        self._disconnect()
        if self.candidate is not None:
            self.candidate.stop()
        self.previous = self.candidate = None
