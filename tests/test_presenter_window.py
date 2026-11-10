from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pdf_presenter.ui.presenter_window import PresenterWindow
from pdf_presenter.ui.styles import apply_theme


@pytest.fixture
def presenter(qtbot, tmp_path, monkeypatch):
    window = PresenterWindow(tmp_path / "appdata")
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.test_errors = errors
    qtbot.addWidget(window)
    apply_theme(QApplication.instance())
    window.show()
    window.activateWindow()
    window.setFocus()
    qtbot.waitUntil(window.isVisible)
    yield window
    window.close()


def load(qtbot, window, path):
    window.load_pdf(str(path))
    qtbot.waitUntil(lambda: window.document is not None and not window.loading, timeout=15000)
    qtbot.waitUntil(lambda: not window.current_slide.image.isNull(), timeout=15000)


def focus(qtbot, window, widget=None):
    window.activateWindow()
    (widget or window).setFocus()
    qtbot.waitUntil(lambda: QApplication.activeWindow() == window)
    QApplication.processEvents()


def wait_slide(qtbot, window, number):
    qtbot.waitUntil(lambda: window.slides.current == number - 1, timeout=5000)
    qtbot.waitUntil(
        lambda: (
            not window.current_slide.image.isNull() and not window.audience.slide.image.isNull()
        ),
        timeout=15000,
    )
    assert window.current_slide.page == window.audience.slide.page == number - 1


def test_keyboard_acceptance_sequence_and_persistence(presenter, qtbot, pdf_factory, tmp_path):
    window = presenter
    path = pdf_factory()
    load(qtbot, window, path)
    window.slides.go_to_number(17)
    focus(qtbot, window, window.notes_panel.editor)
    QTest.keyClicks(window.notes_panel.editor, "My private speaker notes")
    window.notes_panel.font_size.setValue(20)
    qtbot.waitUntil(lambda: not window.notes.dirty, timeout=3000)
    focus(qtbot, window)
    QTest.keyClick(window, Qt.Key.Key_F5, Qt.KeyboardModifier.ShiftModifier)
    wait_slide(qtbot, window, 17)
    assert window.audience.isVisible() and window.presentation.active
    assert window.audience.preview and not window.audience.isFullScreen()
    assert window.timer.running
    audience_id = id(window.audience)
    start = window.timer._started
    focus(qtbot, window)
    QTest.keyClicks(window, "35")
    assert window.number_label.text() == "Перейти: 35 ↵"
    assert window.audience.findChildren(type(window.notes_panel.editor)) == []
    QTest.keyClick(window, Qt.Key.Key_Return)
    wait_slide(qtbot, window, 35)
    window.thumbnails.list.scrollToItem(window.thumbnails.list.item(7))
    QApplication.processEvents()
    rect = window.thumbnails.list.visualItemRect(window.thumbnails.list.item(7))
    QTest.mouseClick(
        window.thumbnails.list.viewport(), Qt.MouseButton.LeftButton, pos=rect.center()
    )
    wait_slide(qtbot, window, 8)
    assert window.timer._started == start and window.timer.elapsed > 0
    focus(qtbot, window)
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert not window.presentation.active and not window.audience.isVisible()
    QTest.keyClick(window, Qt.Key.Key_F5)
    wait_slide(qtbot, window, 1)
    assert id(window.audience) == audience_id
    focus(qtbot, window)
    QTest.keyClick(window, Qt.Key.Key_F5)
    assert id(window.audience) == audience_id
    window.presentation.stop()
    window.slides.go_to_number(17)
    qtbot.waitUntil(lambda: not window.current_slide.image.isNull(), timeout=10000)
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    assert window.grab().save(str(artifacts / "presenter-desktop.png"))
    window.resize(980, 700)
    QApplication.processEvents()
    assert window.grab().save(str(artifacts / "presenter-compact.png"))
    window.close()
    restored = PresenterWindow(tmp_path / "appdata")
    qtbot.addWidget(restored)
    restored.show()
    load(qtbot, restored, path)
    restored.slides.go_to_number(17)
    assert restored.notes_panel.editor.toPlainText() == "My private speaker notes"
    assert restored.notes_panel.font_size.value() == 20
    assert restored.settings.get("recent_files")[0] == str(path)
    restored.close()
    assert not window.test_errors


def test_editor_focus_navigation_and_blank(presenter, qtbot, pdf_factory):
    window = presenter
    load(qtbot, window, pdf_factory())
    window.start_presentation(True)
    focus(qtbot, window, window.notes_panel.editor)
    QTest.keyClicks(window.notes_panel.editor, "25 bw test")
    QTest.keyClick(window.notes_panel.editor, Qt.Key.Key_Return)
    QTest.keyClick(window.notes_panel.editor, Qt.Key.Key_Home)
    QTest.keyClick(window.notes_panel.editor, Qt.Key.Key_Right)
    assert window.slides.current == 0
    assert not window.presentation.number and not window.presentation.blank
    assert "25 bw test" in window.notes_panel.editor.toPlainText()
    focus(qtbot, window.audience)
    QTest.keyClick(window.audience, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: QApplication.focusWidget() == window.notes_panel.editor)
    focus(qtbot, window, window.navigation.jump)
    window.navigation.jump.selectAll()
    QTest.keyClicks(window.navigation.jump, "25")
    QTest.keyClick(window.navigation.jump, Qt.Key.Key_Return)
    wait_slide(qtbot, window, 25)
    focus(qtbot, window)
    QTest.keyClick(window, Qt.Key.Key_B)
    assert window.audience.slide.blank == "black"
    QTest.keyClick(window, Qt.Key.Key_W)
    assert window.audience.slide.blank == "white"
    QTest.keyClick(window, Qt.Key.Key_W)
    assert window.audience.slide.blank == ""
    QTest.keyClicks(window, "99")
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert window.slides.current == 24
    QTest.keyClick(window, Qt.Key.Key_Escape)
    assert window.presentation.active and not window.presentation.number
    # Keyboard controls also work while the audience window owns focus.
    focus(qtbot, window.audience)
    QTest.keyClick(window.audience, Qt.Key.Key_Right)
    wait_slide(qtbot, window, 26)
    QTest.keyClick(window.audience, Qt.Key.Key_Escape)
    assert not window.presentation.active


@pytest.mark.parametrize(
    "key,index",
    [
        (Qt.Key.Key_Left, 15),
        (Qt.Key.Key_Up, 15),
        (Qt.Key.Key_PageUp, 15),
        (Qt.Key.Key_Home, 0),
    ],
)
def test_backward_shortcuts(presenter, qtbot, pdf_factory, key, index):
    load(qtbot, presenter, pdf_factory())
    presenter.slides.go_to_number(17)
    focus(qtbot, presenter)
    QTest.keyClick(presenter, key)
    assert presenter.slides.current == index


@pytest.mark.parametrize(
    "key,index",
    [
        (Qt.Key.Key_Right, 1),
        (Qt.Key.Key_Down, 1),
        (Qt.Key.Key_Space, 1),
        (Qt.Key.Key_PageDown, 1),
        (Qt.Key.Key_End, 49),
    ],
)
def test_forward_shortcuts(presenter, qtbot, pdf_factory, key, index):
    load(qtbot, presenter, pdf_factory())
    focus(qtbot, presenter)
    QTest.keyClick(presenter, key)
    assert presenter.slides.current == index


def test_pause_reset_and_window_visibility(presenter, qtbot, pdf_factory):
    load(qtbot, presenter, pdf_factory(3))
    presenter.start_presentation()
    presenter._pause_timer()
    elapsed = presenter.timer.elapsed
    presenter.slides.next()
    assert presenter.timer.elapsed == elapsed and not presenter.timer.running
    presenter._pause_timer()
    assert presenter.timer.running
    presenter.toggle_audience()
    assert not presenter.audience.isVisible() and presenter.presentation.active
    presenter.toggle_audience()
    assert presenter.audience.isVisible()
    presenter.timer.reset()
    assert presenter.timer.elapsed < 1


def test_password_dialog_retry_and_failed_open_preserves_pdf(
    presenter, qtbot, pdf_factory, monkeypatch, tmp_path
):
    responses = iter([("wrong", True), ("secret", True)])
    monkeypatch.setattr(
        "pdf_presenter.ui.presenter_window.QInputDialog.getText", lambda *args: next(responses)
    )
    path = pdf_factory(2, password="secret")
    load(qtbot, presenter, path)
    assert presenter.document.page_count == 2
    assert not presenter.test_errors
    presenter.load_pdf(str(tmp_path / "missing.pdf"))
    qtbot.waitUntil(lambda: not presenter.loading, timeout=15000)
    assert presenter.document.path == str(path)
    assert len(presenter.test_errors) == 1


def test_save_error_prevents_close_and_pdf_change(presenter, qtbot, pdf_factory, monkeypatch):
    from pdf_presenter.core.storage import StorageError

    path = pdf_factory(2)
    load(qtbot, presenter, path)
    presenter.notes_panel.editor.setPlainText("Must not lose this note")
    original_save = presenter.notes.save

    def fail_save():
        raise StorageError("disk full")

    monkeypatch.setattr(presenter.notes, "save", fail_save)
    presenter.close()
    assert presenter.isVisible() and presenter.notes.dirty
    presenter.load_pdf(str(pdf_factory(1, "other.pdf")))
    assert presenter.document.path == str(path) and not presenter.loading
    monkeypatch.setattr(presenter.notes, "save", original_save)
    assert presenter.save_notes()


def test_open_shortcut_manual_save_and_pdf_drop(presenter, qtbot, pdf_factory, monkeypatch):
    from PySide6.QtCore import QMimeData, QPoint, QPointF, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    first = pdf_factory(3)
    monkeypatch.setattr(
        "pdf_presenter.ui.presenter_window.QFileDialog.getOpenFileName",
        lambda *args: (str(first), "PDF (*.pdf)"),
    )
    focus(qtbot, presenter)
    QTest.keyClick(presenter, Qt.Key.Key_O, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: presenter.document is not None, timeout=15000)
    presenter.notes_panel.editor.setPlainText("Manually saved")
    assert presenter.notes.dirty
    QTest.keyClick(presenter, Qt.Key.Key_S, Qt.KeyboardModifier.ControlModifier)
    assert not presenter.notes.dirty and presenter.notes.path.exists()
    second = pdf_factory(5, "drop.pdf")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(second))])
    drag = QDragEnterEvent(
        QPoint(30, 30),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(presenter, drag)
    assert drag.isAccepted()
    drop = QDropEvent(
        QPointF(30, 30),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(presenter, drop)
    qtbot.waitUntil(lambda: presenter.document.path == str(second), timeout=15000)
    assert presenter.slides.count == 5
    assert presenter.settings.get("recent_files")[:2] == [str(second), str(first)]


def test_resize_keeps_selected_thumbnail_visible(presenter, qtbot, pdf_factory):
    load(qtbot, presenter, pdf_factory())
    presenter.slides.go_to_number(17)
    presenter.resize(980, 650)
    qtbot.waitUntil(
        lambda: (
            presenter.thumbnails.list.viewport()
            .rect()
            .contains(
                presenter.thumbnails.list.visualItemRect(
                    presenter.thumbnails.list.item(16)
                ).center()
            )
        )
    )
