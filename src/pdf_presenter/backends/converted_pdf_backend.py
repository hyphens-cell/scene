from dataclasses import replace

from pdf_presenter.i18n import tr

from ..core.capability_model import COMPATIBILITY_WARNING, BackendCapabilities
from ..services.conversion_service import ConversionService
from .pdf_backend import PDFBackend


class ConvertedPDFBackend(PDFBackend):
    label = "PDF · режим совместимости"

    def __init__(self, kind: str = "pdf_copy", executable: str = "", parent=None) -> None:
        super().__init__(parent)
        self.kind = kind
        self.executable = executable
        self.source = ""
        self.source_fingerprint = ""
        self.source_warnings = []
        self._password = ""
        self.conversion = ConversionService(self)
        self.conversion.completed.connect(self._converted)
        self.conversion.failed.connect(lambda message: self.load_failed.emit("document", message))

    def load(self, file_path: str, password: str = "") -> None:
        self.source = file_path
        self._password = password
        self.conversion.start(file_path, self.executable, self.kind == "pdf_copy")

    def _converted(self, path: str, fingerprint: str, warnings: list[str]) -> None:
        self.source_fingerprint = fingerprint
        self.source_warnings = warnings
        self.renderer.load(path, self._password)
        self._password = ""

    def _loaded(self, source) -> None:
        from ..core.capability_model import PresentationDocument

        self.document = PresentationDocument(
            self.source,
            self.source_fingerprint,
            source.page_count,
            source.title,
            source.page_sizes,
            warnings=(
                tr(COMPATIBILITY_WARNING),
                tr("В PDF-режиме видео, звук, анимации и переходы не воспроизводятся."),
                *self.source_warnings,
            ),
        )
        self.current = 0
        self.loaded.emit(self.document)

    def get_capabilities(self) -> BackendCapabilities:
        return replace(super().get_capabilities(), compatibility=True)

    def dispose(self) -> None:
        self._password = ""
        super().dispose()
        # Renderer must release the converted PDF before its directory is removed.
        self.conversion.close()
