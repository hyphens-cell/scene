"""Set PDFPRESENTER_LIBREOFFICE to a real soffice.com/exe for native conversion tests."""

import hashlib
import os
from pathlib import Path

import pytest

from pdf_presenter.backends.converted_pdf_backend import ConvertedPDFBackend
from pdf_presenter.core.backend_manager import BackendManager, EngineAvailability

pytestmark = pytest.mark.skipif(
    not os.environ.get("PDFPRESENTER_LIBREOFFICE"),
    reason="Explicit installed/extracted LibreOffice path required",
)


@pytest.mark.parametrize("filename", ["native-animation.pptx", "legacy.ppt"])
def test_real_libreoffice_conversion_without_powerpoint(qtbot, filename):
    executable = os.environ["PDFPRESENTER_LIBREOFFICE"]
    source = Path(__file__).parent / "fixtures" / filename
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    manager = BackendManager(EngineAvailability(powerpoint=False, libreoffice=executable))
    choice = manager.choose(str(source))
    backend = manager.create(choice)
    assert isinstance(backend, ConvertedPDFBackend) and backend.kind == "libreoffice_pdf"
    errors, images = [], []
    backend.load_failed.connect(lambda *args: errors.append(args))
    backend.failed.connect(errors.append)
    backend.ready.connect(lambda *args: images.append(args))
    try:
        backend.load(str(source))
        qtbot.waitUntil(lambda: backend.document is not None or bool(errors), timeout=135000)
        assert not errors
        assert backend.document.page_count == 5
        assert backend.document.fingerprint == before
        directory = Path(backend.conversion._directory.name)
        backend.get_preview(1)
        qtbot.waitUntil(lambda: bool(images) or bool(errors), timeout=15000)
        assert not errors and images[0][2].samples
        capabilities = backend.get_capabilities()
        assert capabilities.compatibility and not capabilities.video and not capabilities.animations
        assert any("не воспроизводятся" in warning for warning in backend.document.warnings)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    finally:
        backend.dispose()
    assert not directory.exists()


def test_invalid_presentation_reports_conversion_failure(qtbot, tmp_path):
    source = tmp_path / "damaged.pptx"
    source.write_bytes(b"This is not a PowerPoint presentation")
    backend = ConvertedPDFBackend("libreoffice_pdf", os.environ["PDFPRESENTER_LIBREOFFICE"])
    errors = []
    backend.load_failed.connect(lambda *args: errors.append(args))
    try:
        backend.load(str(source))
        qtbot.waitUntil(lambda: bool(errors) or backend.document is not None, timeout=135000)
        assert errors and backend.document is None
    finally:
        backend.dispose()
