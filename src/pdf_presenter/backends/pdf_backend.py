from __future__ import annotations

from ..core.capability_model import BackendCapabilities, PresentationDocument
from ..core.pdf_document import PdfDocument
from ..core.render_service import RenderService
from .base_backend import PresentationBackend


class PDFBackend(PresentationBackend):
    kind = "pdf"
    label = "PDF"

    def __init__(self, parent=None, budget: int = 96 * 1024 * 1024) -> None:
        super().__init__(parent)
        self.renderer = RenderService(self, budget)
        self.renderer.loaded.connect(self._loaded)
        self.renderer.load_failed.connect(self.load_failed)
        self.renderer.failed.connect(self.failed)
        self.renderer.ready.connect(self.ready)

    @property
    def cache(self):
        return self.renderer.cache

    @property
    def pending_count(self) -> int:
        return self.renderer.pending_count

    def load(self, file_path: str, password: str = "") -> None:
        self.renderer.load(file_path, password)

    def _loaded(self, source: PdfDocument) -> None:
        self.document = PresentationDocument(
            source.path,
            source.fingerprint,
            source.page_count,
            source.title,
            source.page_sizes,
            warnings=source.warnings,
        )
        self.current = 0
        self.loaded.emit(self.document)

    def get_capabilities(self) -> BackendCapabilities:
        return BackendCapabilities()

    def start(self, slide_index: int) -> None:
        if self.go_to_slide(slide_index):
            self.active = True
            self.started.emit()

    def stop(self) -> None:
        self.active = False
        self.stopped.emit()

    def next(self) -> bool:
        if self.current + 1 >= self.get_slide_count():
            if self.active:
                self.ended.emit()
            return False
        return self.go_to_slide(self.current + 1)

    def previous(self) -> bool:
        return self.go_to_slide(self.current - 1)

    def go_to_slide(self, index: int) -> bool:
        if not 0 <= index < self.get_slide_count():
            return False
        self.current = index
        self.position_changed.emit(index)
        return True

    def begin_frame(self) -> None:
        self.renderer.begin_frame()

    def request(self, tag: str, page: int, width: int, height: int, priority: int = 0) -> None:
        self.renderer.request(tag, page, width, height, priority)

    def dispose(self) -> None:
        if not self.disposed:
            self.stop()
            self.renderer.close()
            self.disposed = True
