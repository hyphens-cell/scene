import hashlib

import pytest

from pdf_presenter.core.pdf_document import DocumentError, PasswordRequired, open_pdf
from pdf_presenter.core.render_service import render_page


def test_metadata_hash_and_mixed_orientations(pdf_factory):
    path = pdf_factory()
    info, document = open_pdf(str(path))
    try:
        assert info.page_count == 50
        assert info.fingerprint == hashlib.sha256(path.read_bytes()).hexdigest()
        assert info.page_sizes[0] == (540, 760)
        assert info.page_sizes[1] == (960, 540)
        for page in (0, 1):
            raster = render_page(document, (page, 1000, 600))
            assert raster.width <= 1001 and raster.height <= 601
            width, height = info.page_sizes[page]
            assert abs(raster.width / raster.height - width / height) < 0.005
            assert len(raster.samples) == raster.stride * raster.height
    finally:
        document.close()
    assert document.is_closed


def test_password_and_wrong_password(pdf_factory):
    path = pdf_factory(2, password="secret")
    for password in ("", "wrong"):
        with pytest.raises(PasswordRequired):
            open_pdf(str(path), password)
    info, document = open_pdf(str(path), "secret")
    assert info.page_count == 2
    document.close()


def test_corrupt_and_missing_pdf(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4\nbroken data")
    for filename in (path, tmp_path / "absent.pdf"):
        with pytest.raises(DocumentError):
            open_pdf(str(filename))


def test_content_identity_survives_rename(pdf_factory, tmp_path):
    path = pdf_factory(1)
    first, document = open_pdf(str(path))
    document.close()
    renamed = path.rename(tmp_path / "renamed.pdf")
    second, document = open_pdf(str(renamed))
    document.close()
    assert first.fingerprint == second.fingerprint
