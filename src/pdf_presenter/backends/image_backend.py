from PySide6.QtCore import QRectF

from ..core.capability_model import BackendCapabilities
from ..core.media_layout import media_rect
from .pdf_backend import PDFBackend


class ImageBackend(PDFBackend):
    kind = "image"
    label = "Изображение"

    def load(self, file_path: str, password: str = "") -> None:
        self.renderer.load(file_path, kind="image")

    def get_capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(scaling=True)

    def request(self, tag, page, width, height, priority=0):
        if self.document and tag in {"audience", "current"}:
            rect = media_rect(
                QRectF(0, 0, width, height), self.document.page_sizes[0], self.media_settings
            )
            width, height = max(width, round(rect.width())), max(height, round(rect.height()))
        super().request(tag, page, width, height, priority)
