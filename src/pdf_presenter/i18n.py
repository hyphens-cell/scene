"""Russian source strings with an English catalog; no changes to user content.

Language is fixed for a running session. SCENE_LANGUAGE also propagates it to
spawned PDF, Office and Canva workers. A menu selection takes effect next launch.
"""

import json
import os
from pathlib import Path

LANGUAGES = {"ru": "Русский", "en": "English"}
_language = os.environ.get("SCENE_LANGUAGE", "ru")
if _language not in LANGUAGES:
    _language = "ru"
_english = json.loads(
    (Path(__file__).parent / "resources" / "locales" / "en.json").read_text(encoding="utf-8")
)


def language() -> str:
    return _language


def set_language(value: str) -> None:
    global _language
    _language = value if value in LANGUAGES else "ru"
    os.environ["SCENE_LANGUAGE"] = _language


def tr(source: str, **values: object) -> str:
    template = _english.get(source, source) if _language == "en" else source
    return template.format(**values) if values else template


def initialize_language(root: Path | None = None) -> None:
    from .core.settings_manager import SettingsManager

    set_language(os.environ.get("SCENE_LANGUAGE") or SettingsManager(root).get("language", "ru"))


def install_qt_translations(app) -> None:
    """Translate Qt's standard dialog buttons without translating document text."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

    QLocale.setDefault(QLocale("ru_RU" if language() == "ru" else "en_US"))
    previous = getattr(app, "_scene_translator", None)
    if previous is not None:
        app.removeTranslator(previous)
        previous.deleteLater()
    translator = QTranslator(app)
    directory = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load("qtbase_" + language(), directory):
        app.installTranslator(translator)
    # QApplication owns the C++ object; retain the Python wrapper as well.
    app._scene_translator = translator
