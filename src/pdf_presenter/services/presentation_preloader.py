from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from ..core.presentation_queue import PresentationItem, QueueState

log = logging.getLogger(__name__)


class PresentationPreloader(QObject):
    """Holds at most one candidate in addition to the active presentation.

    A candidate becomes usable only after its first preview is actually rendered.
    Failed/obsolete loads never replace the current document or audience surface.
    """

    prepared = Signal(str, object, object)
    failed = Signal(str, str, str)

    def __init__(self, manager, queue, parent=None) -> None:
        super().__init__(parent)
        self.manager, self.queue = manager, queue
        self.backend = None
        self.item_id = ""
        self.ready = False
        self.preview = None

    def prepare(self, item: PresentationItem, password: str = "") -> None:
        if self.item_id == item.id and self.backend and not password:
            if self.ready:
                self.prepared.emit(item.id, self.backend, self.preview)
            return
        self.cancel()
        self.item_id = item.id
        self.queue.update(item.id, state=QueueState.CHECKING, error="")
        try:
            choice = self.manager.choose(item.path, item.preferred_backend)
            backend = self.manager.create(choice, self)
            self.backend = backend
            backend.set_media_settings(item.media_settings)
            self.queue.update(
                item.id,
                state=QueueState.PREPARING,
                backend=choice.kind,
                warnings=[choice.warning] if choice.warning else [],
            )
            backend.loaded.connect(lambda document: self._loaded(backend, item.id, document))
            backend.ready.connect(
                lambda tag, page, raster: self._raster(backend, item.id, tag, page, raster)
            )
            backend.load_failed.connect(
                lambda kind, message: self._failed(backend, item.id, kind, message)
            )
            backend.failed.connect(
                lambda message: self._failed(backend, item.id, "document", message)
            )
            backend.load(item.path, password)
        except Exception as exc:
            log.exception("Presentation preparation failed")
            self._failed(self.backend, item.id, "document", str(exc))

    def _loaded(self, backend, item_id, document) -> None:
        if backend is not self.backend or item_id != self.item_id:
            return
        item = self.queue.get(item_id)
        if item is None:
            self.cancel()
            return
        item.last_slide = min(item.last_slide, max(0, document.page_count - 1))
        warnings = list(dict.fromkeys([*item.warnings, *document.warnings]))
        self.queue.update(
            item_id,
            slide_count=document.page_count,
            notes_ref=document.fingerprint,
            warnings=warnings,
        )
        if not backend.get_capabilities().preview:
            self._finish(backend, item_id, None)
        else:
            backend.request("prepared", item.last_slide, 1280, 800, priority=0)

    def _raster(self, backend, item_id, tag, page, raster) -> None:
        if backend is self.backend and item_id == self.item_id and tag == "prepared":
            self._finish(backend, item_id, (page, raster))

    def _finish(self, backend, item_id, preview) -> None:
        self.ready = True
        self.preview = preview
        self.queue.update(item_id, state=QueueState.READY)
        self.prepared.emit(item_id, backend, preview)

    def _failed(self, backend, item_id, kind, message) -> None:
        if backend is not self.backend or item_id != self.item_id:
            return
        self.queue.update(item_id, state=QueueState.ERROR, error=message)
        # Release the failed candidate before reporting the error: the handler
        # may immediately retry this item (including a password prompt).
        try:
            self.cancel()
        except Exception:
            log.exception("Failed to release unsuccessful presentation candidate")
        self.failed.emit(item_id, kind, message)

    def take(self, item_id: str):
        if item_id != self.item_id or not self.ready:
            return None
        backend, preview = self.backend, self.preview
        self.backend = None
        self.item_id = ""
        self.preview = None
        self.ready = False
        return backend, preview

    def cancel(self) -> None:
        backend, item_id = self.backend, self.item_id
        self.backend = None
        self.item_id = ""
        self.ready = False
        self.preview = None
        if backend is not None:
            try:
                backend.dispose()
            finally:
                backend.deleteLater()
        item = self.queue.get(item_id)
        if item and item.state in (QueueState.CHECKING, QueueState.PREPARING):
            self.queue.update(item_id, state=QueueState.WAITING)

    def close(self) -> None:
        self.cancel()
