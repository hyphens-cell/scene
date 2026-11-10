from unittest.mock import Mock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from pdf_presenter.core.capability_model import BackendCapabilities
from pdf_presenter.ui.presenter_window import PresenterWindow


@pytest.fixture
def media_window(qtbot, tmp_path, pdf_factory, monkeypatch):
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.show()
    window.load_pdf(str(pdf_factory(3)))
    qtbot.waitUntil(lambda: window.document is not None and not window.loading, timeout=15000)
    monkeypatch.setattr(
        window.renderer, "get_capabilities", lambda: BackendCapabilities(video_controls=True)
    )
    command = Mock(return_value=True)
    monkeypatch.setattr(window.renderer, "control_video", command)
    window.start_presentation()
    window.navigation.media.show()
    window.navigation.media.update_state(
        0,
        [
            {
                "id": 3,
                "name": "Clip",
                "state": 0,
                "position": 4000,
                "duration": 12000,
                "volume": 50,
                "seekable": True,
            }
        ],
    )
    window.navigation.media.set_available(True)
    window.activateWindow()
    qtbot.waitUntil(lambda: QApplication.activeWindow() == window)
    yield window, command
    window._project_dirty = False
    window.close()
    assert not errors


@pytest.mark.parametrize("control", ["play", "seek", "volume"])
def test_player_focus_keeps_blank_and_escape_available(media_window, qtbot, control):
    window, command = media_window
    widget = getattr(window.navigation.media, control)
    for key, color in [(Qt.Key.Key_B, "black"), (Qt.Key.Key_W, "white")]:
        widget.setFocus()
        qtbot.waitUntil(lambda: QApplication.focusWidget() is widget)
        qtbot.keyClick(widget, key)
        assert window.audience.slide.blank == color
        assert window.presentation.active and window.slides.current == 0
        window.setFocus()
        qtbot.keyClick(window, key)
        assert window.audience.slide.blank == ""
    widget.setFocus()
    qtbot.keyClick(widget, Qt.Key.Key_Escape)
    assert not window.presentation.active and not window.audience.isVisible()
    command.assert_not_called()


def test_player_owns_space_and_seek_arrows(media_window, qtbot):
    window, command = media_window
    window.navigation.media.play.setFocus()
    qtbot.keyClick(window.navigation.media.play, Qt.Key.Key_Space)
    command.assert_called_once_with("pause", 3, slide_index=0, value=0)
    command.reset_mock()
    window.navigation.media.seek.setFocus()
    qtbot.keyClick(window.navigation.media.seek, Qt.Key.Key_Right)
    command.assert_called_once_with("seek", 3, slide_index=0, value=5000)
    assert window.slides.current == 0 and window.presentation.active


def test_escape_stops_show_while_next_file_is_loading(media_window, qtbot, pdf_factory):
    window, _ = media_window
    window.load_pdf(str(pdf_factory(4, "next.pdf")))
    assert window.loading and window.presentation.active
    window.setFocus()
    qtbot.keyClick(window, Qt.Key.Key_Escape)
    assert not window.presentation.active and not window.audience.isVisible()
