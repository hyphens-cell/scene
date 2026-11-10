"""Opt-in executable acceptance harness; never invoked during normal startup."""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from . import __version__
from .i18n import language, tr
from .ui.presenter_window import PresenterWindow


def run_smoke_test(app: QApplication, output: Path) -> int:
    import pymupdf

    output.mkdir(parents=True, exist_ok=True)
    if app.platformName() == "offscreen":
        for name in ("segoeui.ttf", "segoeuib.ttf", "consola.ttf"):
            path = Path("C:/Windows/Fonts") / name
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))
    pdf = output / "acceptance-50-slides.pdf"
    with pymupdf.open() as document:
        for number in range(50):
            page = document.new_page(width=960, height=540)
            page.draw_rect(page.rect, color=(0.08, 0.12, 0.2), fill=(0.08, 0.12, 0.2))
            page.insert_text((64, 105), "PDF PRESENTER", fontsize=18, color=(0.4, 0.65, 1))
            page.insert_text((64, 270), f"Slide {number + 1:02}", fontsize=68, color=(1, 1, 1))
            page.insert_text(
                (64, 470), "Windows executable acceptance test", fontsize=18, color=(0.6, 0.7, 0.8)
            )
        document.save(pdf)

    window = PresenterWindow(output / "appdata")
    app.setQuitOnLastWindowClosed(False)
    errors: list[str] = []
    window._warning = errors.append
    window.renderer.load_failed.connect(lambda kind, message: errors.append(message))
    window.renderer.failed.connect(errors.append)
    report: dict[str, object] = {
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "language": language(),
        "file_menu": window.menuBar().actions()[0].text(),
        "platform": app.platformName(),
        "screens": [
            {
                "name": s.name(),
                "width": s.geometry().width(),
                "height": s.geometry().height(),
                "scale": s.devicePixelRatio(),
            }
            for s in app.screens()
        ],
        "steps": [],
    }
    steps = report["steps"]
    state = {"step": 0, "since": time.monotonic(), "timer_start": None, "audience": None}
    ticker = QTimer()
    ticker.setInterval(80)

    def finish(error: str | None = None) -> None:
        ticker.stop()
        if error:
            errors.append(error)
        window.close()
        report["success"] = not errors
        report["errors"] = errors
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        app.exit(1 if errors else 0)

    def focus_presenter() -> None:
        window.activateWindow()
        window.setFocus()
        app.processEvents()

    def images_ready() -> bool:
        return not window.current_slide.image.isNull() and not window.audience.slide.image.isNull()

    def tick() -> None:
        try:
            if errors:
                finish()
                return
            if time.monotonic() - state["since"] > 60:
                raise TimeoutError(f"Acceptance step {state['step']} timed out")
            step = state["step"]
            if step == 0:
                if window.document is None or window.current_slide.image.isNull():
                    return
                assert window.document.page_count == 50
                steps.append("Opened and rendered a real 50-page PDF")
                window.slides.go_to_number(17)
                window.notes_panel.editor.setPlainText("Private notes for slide 17")
                assert window.save_notes()
                focus_presenter()
                QTest.keyClick(window, Qt.Key.Key_F5, Qt.KeyboardModifier.ShiftModifier)
            elif step == 1:
                if not images_ready():
                    return
                assert window.presentation.active and window.audience.slide.page == 16
                state["timer_start"] = window.timer._started
                state["audience"] = id(window.audience)
                if len(app.screens()) > 1:
                    assert window.audience.isFullScreen()
                    assert window.audience.screen() != window.screen()
                    steps.append("Audience fullscreen on second monitor")
                else:
                    assert window.audience.preview and not window.audience.isFullScreen()
                    steps.append("Single-monitor windowed preview")
                steps.append("Shift+F5 started slide 17")
                focus_presenter()
                QTest.keyClicks(window, "35")
                QTest.keyClick(window, Qt.Key.Key_Return)
            elif step == 2:
                if not images_ready():
                    return
                assert window.slides.current == 34 and window.audience.slide.page == 34
                steps.append("Keyboard 35 + Enter synchronized both windows")
                window.thumbnails.list.scrollToItem(window.thumbnails.list.item(7))
                app.processEvents()
                rect = window.thumbnails.list.visualItemRect(window.thumbnails.list.item(7))
                QTest.mouseClick(
                    window.thumbnails.list.viewport(), Qt.MouseButton.LeftButton, pos=rect.center()
                )
            elif step == 3:
                if not images_ready():
                    return
                if (
                    window.next_slide.image.isNull()
                    or window.thumbnails.list.item(7).icon().isNull()
                ):
                    return
                assert window.slides.current == 7 and window.audience.slide.page == 7
                assert window.timer._started == state["timer_start"] and window.timer.running
                steps.append("Thumbnail 8 synchronized both windows without resetting timer")
                assert window.grab().save(str(output / "presenter.png"))
                assert window.audience.grab().save(str(output / "audience.png"))
                focus_presenter()
                QTest.keyClick(window, Qt.Key.Key_Escape)
                assert not window.presentation.active
                QTest.keyClick(window, Qt.Key.Key_F5)
            elif step == 4:
                if not images_ready():
                    return
                assert window.slides.current == 0 and window.audience.slide.page == 0
                assert id(window.audience) == state["audience"]
                steps.append("Esc then F5 restarted slide 1 using the same audience window")
                window.presentation.stop()
                from .core.notes_manager import NotesManager
                from .core.settings_manager import SettingsManager

                assert (
                    NotesManager(window.document.fingerprint, output / "appdata").get(16)
                    == "Private notes for slide 17"
                )
                assert SettingsManager(output / "appdata").get("recent_files")
                steps.append("Notes and settings persisted to disk")
                assert window.menuBar().actions()[0].text() == tr("Файл")
                assert window.navigation.media.play.text() == tr("Пуск")
                assert window.windowTitle().endswith(tr("Сцена"))
                steps.append("Localized menu, player and window title verified")
                finish()
                return
            state["step"] += 1
            state["since"] = time.monotonic()
        except Exception:
            finish(traceback.format_exc())

    window.show()
    window.load_pdf(str(pdf))
    ticker.timeout.connect(tick)
    ticker.start()
    return app.exec()
