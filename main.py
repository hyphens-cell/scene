"""Source and PyInstaller entry point; freeze_support must precede Qt imports."""

import multiprocessing
import sys
from pathlib import Path

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
    from pdf_presenter.app import main

    raise SystemExit(main())
