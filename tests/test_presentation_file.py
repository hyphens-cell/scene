import zipfile
from pathlib import Path

import pytest

from pdf_presenter.core.presentation_file import COMPOUND_HEADER, validate_presentation_file


def test_real_generated_presentations_have_supported_containers():
    for name in ("native-animation.pptx", "legacy.ppt"):
        validate_presentation_file(Path(__file__).parent / "fixtures" / name)


@pytest.mark.parametrize("suffix", [".pptx", ".ppt"])
def test_renamed_text_never_enters_office_import(suffix, tmp_path):
    source = tmp_path / ("renamed" + suffix)
    source.write_bytes(b"ordinary text with wrong extension")
    with pytest.raises(RuntimeError, match="повреждён"):
        validate_presentation_file(source)


def test_encrypted_pptx_is_reported_without_a_password_dialog(tmp_path):
    source = tmp_path / "encrypted.pptx"
    source.write_bytes(COMPOUND_HEADER + b"encrypted payload")
    with pytest.raises(RuntimeError, match="паролем"):
        validate_presentation_file(source)


def test_word_document_zip_renamed_to_pptx_is_rejected(tmp_path):
    source = tmp_path / "not-slides.pptx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    with pytest.raises(RuntimeError, match="не является презентацией"):
        validate_presentation_file(source)
