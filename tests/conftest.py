import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
import pytest


@pytest.fixture(scope="session", autouse=True)
def offscreen_fonts(qapp):
    # The offscreen Windows plugin has no system-font integration.
    from pathlib import Path

    from PySide6.QtGui import QFontDatabase

    for filename in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
        path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


@pytest.fixture
def pdf_factory(tmp_path):
    def create(count=50, filename="slides.pdf", password=None):
        path = tmp_path / filename
        with pymupdf.open() as document:
            for number in range(count):
                width, height = (960, 540) if number % 3 else (540, 760)
                page = document.new_page(width=width, height=height)
                color = ((number % 5) / 8, (number % 7) / 10, 0.25)
                page.draw_rect(page.rect, fill=color, color=color)
                page.insert_text((40, 80), f"Slide {number + 1}", fontsize=28, color=(1, 1, 1))
            options = {}
            if password:
                options = dict(
                    encryption=pymupdf.PDF_ENCRYPT_AES_256,
                    user_pw=password,
                    owner_pw="owner-secret",
                )
            document.save(path, **options)
        return path

    return create
