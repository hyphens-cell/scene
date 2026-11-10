from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

from pdf_presenter.i18n import initialize_language, install_qt_translations, tr


def configure_logging(root: Path | None = None) -> None:
    import logging
    from logging.handlers import RotatingFileHandler

    from .core.storage import data_directory

    try:
        directory = (root if root is not None else data_directory()) / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            directory / "pdf-presenter.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)
    except OSError:
        logging.basicConfig(level=logging.WARNING)


def main() -> int:
    multiprocessing.freeze_support()
    diagnostic = len(sys.argv) >= 3 and sys.argv[1] in {
        "--self-test",
        "--office-self-test",
        "--media-self-test",
        "--canva-self-test",
    }
    configure_logging(Path(sys.argv[2]).resolve() / "appdata" if diagnostic else None)
    root = Path(sys.argv[2]).resolve() / "appdata" if diagnostic else None
    initialize_language(root)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PDFPresenter.Desktop.1")
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from .ui.presenter_window import PresenterWindow
    from .ui.styles import apply_theme

    app = QApplication(sys.argv)
    install_qt_translations(app)
    app.setApplicationName(tr("Сцена"))
    app.setOrganizationName("PDFPresenter")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "resources" / "icons" / "scene.ico")))
    apply_theme(app)
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from .smoke_test import run_smoke_test

        return run_smoke_test(app, Path(sys.argv[2]).resolve())
    if len(sys.argv) == 4 and sys.argv[1] == "--office-self-test":
        from .office_smoke_test import run_office_smoke_test

        return run_office_smoke_test(app, Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())
    if len(sys.argv) == 4 and sys.argv[1] == "--media-self-test":
        from .media_smoke_test import run_media_smoke_test

        return run_media_smoke_test(app, Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())
    if len(sys.argv) == 4 and sys.argv[1] == "--canva-self-test":
        from .canva_smoke_test import run_canva_smoke_test

        return run_canva_smoke_test(app, Path(sys.argv[2]).resolve(), sys.argv[3])
    window = PresenterWindow()
    window.show()
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        from .core.canva_url import is_canva_url, normalize_canva_url

        filename = (
            normalize_canva_url(sys.argv[1])
            if is_canva_url(sys.argv[1])
            else str(Path(sys.argv[1]).resolve())
        )
        if Path(filename).suffix.lower() == ".pdfpresenter":
            QTimer.singleShot(0, lambda: window.open_project(filename))
        else:
            QTimer.singleShot(0, lambda: window.load_pdf(filename))
    return app.exec()
