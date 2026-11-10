"""Opt-in native Windows acceptance: QT_QPA_PLATFORM=windows pytest this file."""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pdf_presenter.ui.presenter_window import PresenterWindow
from pdf_presenter.ui.styles import apply_theme


def test_native_dual_screen_placement_swap_and_fallback(
    qtbot, qapp, tmp_path, pdf_factory, monkeypatch
):
    if qapp.platformName() != "windows" or len(qapp.screens()) < 2:
        pytest.skip("Requires the native Windows platform and two connected screens")
    apply_theme(qapp)
    window = PresenterWindow(tmp_path / "appdata")
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.show()
    window.load_pdf(str(pdf_factory()))
    qtbot.waitUntil(lambda: window.document is not None, timeout=15000)
    window.slides.go_to_number(17)
    window.activateWindow()
    window.setFocus()
    qtbot.waitUntil(lambda: qapp.activeWindow() == window)
    QTest.keyClick(window, Qt.Key.Key_F5, Qt.KeyboardModifier.ShiftModifier)
    qtbot.waitUntil(lambda: window.audience.isFullScreen())
    qtbot.waitUntil(lambda: not window.audience.slide.image.isNull(), timeout=15000)
    assert window.audience.windowHandle().screen() != window.windowHandle().screen()
    assert window.audience.slide.page == 16
    audience_object = window.audience
    started = window.timer._started
    window.activateWindow()
    window.setFocus()
    QApplication.processEvents()
    QTest.keyClicks(window, "35")
    QTest.keyClick(window, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: window.audience.slide.page == 34)
    window.thumbnails.list.setCurrentRow(7)
    qtbot.waitUntil(lambda: not window.audience.slide.image.isNull(), timeout=15000)
    assert window.audience.slide.page == 7
    assert window.timer._started == started
    qtbot.waitUntil(
        lambda: not window.current_slide.image.isNull() and not window.next_slide.image.isNull(),
        timeout=15000,
    )
    qtbot.waitUntil(lambda: not window.thumbnails.list.item(7).icon().isNull(), timeout=15000)
    artifacts = Path("artifacts")
    artifacts.mkdir(exist_ok=True)
    assert window.audience.grab().save(str(artifacts / "audience-native.png"))
    assert window.grab().save(str(artifacts / "presenter-native.png"))
    first_presenter, first_audience = window.screen(), window.audience.screen()
    window.swap_monitors()
    qtbot.waitUntil(lambda: window.screen() == first_audience)
    qtbot.waitUntil(lambda: window.audience.screen() == first_presenter)
    assert window.audience.isFullScreen() and window.audience is audience_object
    # Simulate the screen inventory after unplugging the audience display.
    monkeypatch.setattr(window.monitors, "screens", lambda: [window.screen()])
    window.monitors.changed.emit()
    qtbot.waitUntil(lambda: window.audience.preview)
    assert not window.audience.isFullScreen()
    assert window.presentation.active and window.timer._started == started
    window.presentation.stop()
    window.start_presentation()
    assert window.slides.current == 0
    window.close()
    assert not errors
