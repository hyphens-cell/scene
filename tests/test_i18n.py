import ast
import json
import multiprocessing
import re
from pathlib import Path
from string import Formatter

import pytest
from PySide6.QtWidgets import QDialogButtonBox, QMessageBox

from pdf_presenter import i18n
from pdf_presenter.core.settings_manager import SettingsManager
from pdf_presenter.core.storage import StorageError

ROOT = Path(__file__).parents[1] / "src" / "pdf_presenter"


@pytest.fixture(autouse=True)
def restore_language(monkeypatch):
    previous = i18n.language()
    monkeypatch.setenv("SCENE_LANGUAGE", previous)
    yield
    i18n.set_language(previous)


def test_catalog_coverage_and_format_contracts():
    catalog = json.loads((ROOT / "resources/locales/en.json").read_text(encoding="utf-8"))

    def fields(text):
        return sorted((name, spec, conv) for _, name, spec, conv in Formatter().parse(text) if name)

    for source, english in catalog.items():
        assert english and not re.search("[А-Яа-яЁё]", english), source
        assert fields(source) == fields(english), source
    for path in ROOT.rglob("*.py"):
        if path.name.endswith("smoke_test.py") or path.name == "i18n.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
            ):
                if isinstance(node.args[0], ast.Constant):
                    assert node.args[0].value in catalog, (path, node.lineno)


def test_saved_language_and_environment_override(tmp_path, monkeypatch):
    settings = SettingsManager(tmp_path)
    settings.set("language", "en")
    settings.save()
    monkeypatch.delenv("SCENE_LANGUAGE", raising=False)
    i18n.initialize_language(tmp_path)
    assert i18n.language() == "en"
    assert i18n.tr("Сцена") == "Scene"
    monkeypatch.setenv("SCENE_LANGUAGE", "ru")
    i18n.initialize_language(tmp_path)
    assert i18n.tr("Сцена") == "Сцена"
    assert SettingsManager._valid({"version": 1, "settings": {}})
    assert not SettingsManager._valid({"version": 1, "settings": {"language": "xx"}})


def test_qt_standard_buttons_follow_language(qapp, qtbot):
    for code, expected in (("ru", "Отмена"), ("en", "Cancel")):
        i18n.set_language(code)
        i18n.install_qt_translations(qapp)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        qtbot.addWidget(buttons)
        assert (
            buttons.button(QDialogButtonBox.StandardButton.Cancel).text().replace("&", "")
            == expected
        )


@pytest.mark.parametrize("code", ["ru", "en"])
def test_presenter_language_preserves_user_content(qtbot, qapp, tmp_path, pdf_factory, code):
    from pdf_presenter.ui.presenter_window import PresenterWindow
    from pdf_presenter.ui.styles import apply_theme

    i18n.set_language(code)
    i18n.install_qt_translations(qapp)
    apply_theme(qapp)
    window = PresenterWindow(tmp_path / "settings")
    qtbot.addWidget(window)
    window.show()
    errors = []
    window._warning = errors.append
    path = pdf_factory(3, filename="Доклад — Report.pdf")
    window.load_pdf(str(path))
    qtbot.waitUntil(lambda: window.document is not None or bool(errors), timeout=20000)
    assert not errors
    assert window.queue.items[0].name == path.name
    window.notes_panel.editor.setPlainText("Мои заметки / My notes {p0}")
    assert window.save_notes()
    assert window.navigation.media.play.text() == ("Play" if code == "en" else "Пуск")
    assert window.menuBar().actions()[0].text() == ("File" if code == "en" else "Файл")
    assert window.windowTitle().endswith("Scene" if code == "en" else "Сцена")
    assert window.notes_panel.editor.toPlainText() == "Мои заметки / My notes {p0}"
    output = Path("artifacts/localization")
    output.mkdir(parents=True, exist_ok=True)
    for width, height in ((1440, 900), (900, 650)):
        window.resize(width, height)
        qtbot.wait(100)
        assert window.grab().save(str(output / f"{code}-{width}.png"))
    window._project_dirty = False
    window.close()


def test_language_selection_does_not_interrupt_session(qtbot, tmp_path, monkeypatch):
    from pdf_presenter.ui.presenter_window import PresenterWindow

    i18n.set_language("ru")
    window = PresenterWindow(tmp_path)
    qtbot.addWidget(window)
    notices = []
    monkeypatch.setattr(QMessageBox, "information", lambda *args: notices.append(args[-1]))
    window._select_language("en")
    assert SettingsManager(tmp_path).get("language") == "en"
    assert i18n.language() == "ru"
    assert not window._closing
    assert notices
    errors = []
    window._warning = errors.append
    window.settings.read_only = True
    window._select_language("ru")
    assert window.settings.get("language") == "en"
    assert errors
    window.close()


def _worker_translation(pipe):
    pipe.send((i18n.language(), i18n.tr("Не удалось открыть PDF: {p0}", p0="report.pdf")))
    pipe.close()


def test_spawned_worker_inherits_language():
    i18n.set_language("en")
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe()
    process = ctx.Process(target=_worker_translation, args=(child,))
    try:
        process.start()
        child.close()
        assert parent.poll(15)
        assert parent.recv() == ("en", "Could not open PDF: report.pdf")
        process.join(10)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        parent.close()


def test_english_errors_and_deferred_labels(tmp_path):
    from pdf_presenter.backends.image_backend import ImageBackend
    from pdf_presenter.core.pdf_document import DocumentError, open_pdf
    from pdf_presenter.core.presentation_queue import PresentationItem
    from pdf_presenter.core.project_manager import EventProject
    from pdf_presenter.ui.presentation_item_widget import presentation_item_text

    i18n.set_language("en")
    assert EventProject().name == "New event"
    assert ImageBackend().label == "Image"
    assert "Waiting to load" in presentation_item_text(PresentationItem("example.pdf"))
    with pytest.raises(DocumentError, match="Could not open PDF"):
        open_pdf(str(tmp_path / "missing.pdf"))
    settings = SettingsManager(tmp_path)
    settings.read_only = True
    with pytest.raises(StorageError, match="Settings are damaged"):
        settings.save()
