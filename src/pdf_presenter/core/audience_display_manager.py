from __future__ import annotations

import logging
import sys
from enum import StrEnum

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter

from pdf_presenter.i18n import tr

from .capability_model import DisplayTarget


class AudienceMode(StrEnum):
    SLIDE = "slide"
    BLACK = "black"
    WHITE = "white"
    SPLASH = "splash"
    HOLD = "hold"


class AudienceDisplayManager(QObject):
    changed = Signal(str)

    def __init__(self, window, monitors, presenter, parent=None) -> None:
        super().__init__(parent)
        self.window, self.monitors, self.presenter = window, monitors, presenter
        self.mode = AudienceMode.SLIDE
        self.backend = None
        self.last_image = QImage()
        self.splash_text = tr("Добро пожаловать")
        self.native_hwnd = 0
        self.visible = False
        self.handoff = False

    def place(self, screen) -> DisplayTarget:
        preview = self.monitors.requires_preview(screen, self.presenter.screen())
        if (
            not self.window.isVisible()
            or self.window.screen() != screen
            or self.window.preview != preview
        ):
            self.window.display_on(screen, preview)
        self.visible = True
        area = screen.geometry()
        device = ""
        if sys.platform == "win32" and not screen.name() == "":
            try:
                import win32api

                monitor = win32api.MonitorFromWindow(int(self.window.winId()), 2)
                device = win32api.GetMonitorInfo(monitor)["Device"]
            except Exception:
                pass
        return DisplayTarget(
            screen.name(),
            area.x(),
            area.y(),
            area.width(),
            area.height(),
            preview,
            int(self.window.winId()),
            device,
        )

    def _cover(self, enabled: bool) -> None:
        if sys.platform == "win32" and self.window.windowHandle() and self.window.isVisible():
            try:
                import win32con
                import win32gui

                win32gui.SetWindowPos(
                    int(self.window.winId()),
                    win32con.HWND_TOPMOST if enabled else win32con.HWND_NOTOPMOST,
                    0,
                    0,
                    0,
                    0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
                )
                if not enabled and self.native_hwnd and win32gui.IsWindow(self.native_hwnd):
                    win32gui.SetWindowPos(
                        self.native_hwnd,
                        win32con.HWND_TOPMOST if not self.window.preview else win32con.HWND_TOP,
                        0,
                        0,
                        0,
                        0,
                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
                    )
                return
            except Exception:
                pass
        if enabled:
            self.window.raise_()

    def hold(self) -> None:
        self._remember_visible_frame()
        self.handoff = True
        self.window.slide.set_media_view()
        self.window.slide.image = self.last_image.copy()
        if self.mode in (AudienceMode.BLACK, AudienceMode.WHITE):
            self.window.slide.set_blank(self.mode.value)
        else:
            self.window.slide.set_blank("" if not self.last_image.isNull() else "black")
        self._cover(True)
        if self.backend is not None and self.backend.get_capabilities().native_window:
            self.backend.set_blank("pause")

    def _remember_visible_frame(self) -> None:
        if self.native_hwnd and sys.platform == "win32" and self.mode == AudienceMode.SLIDE:
            try:
                from ..services.audience_capture import capture_show

                frame = capture_show(self.native_hwnd)
                if not frame.isNull():
                    self.last_image = frame
                    return
            except Exception:
                logging.getLogger(__name__).info(
                    "Native frame unavailable; retaining slide preview", exc_info=True
                )
        if not self.window.slide.image.isNull():
            # Capture the composed crop/letterbox, not the unscaled source image.
            self.last_image = self.window.slide.grab().toImage()

    def restore_slide_view(self):
        backend = self.backend
        if backend and backend.document and backend.get_capabilities().scaling:
            self.window.slide.set_media_view(backend.document.page_sizes[0], backend.media_settings)
        else:
            self.window.slide.set_media_view()

    def attach(self, backend) -> None:
        self.backend = backend
        self.native_hwnd = getattr(backend, "native_hwnd", 0)
        self.handoff = False
        self.apply_mode(self.mode)

    def apply_mode(self, mode: AudienceMode | str) -> None:
        mode = AudienceMode(mode)
        if mode == AudienceMode.HOLD and self.mode != AudienceMode.HOLD:
            self._remember_visible_frame()
        self.mode = mode
        if self.handoff:
            return
        native = self.backend is not None and self.backend.get_capabilities().native_window
        if mode == AudienceMode.SLIDE:
            self.restore_slide_view()
            self.window.slide.set_blank("")
            if native:
                self.backend.set_blank("")
            self._cover(not native)
        elif mode in (AudienceMode.BLACK, AudienceMode.WHITE):
            self.window.slide.set_blank(mode.value)
            if native:
                self.backend.set_blank(mode.value)
            self._cover(True)
        elif mode == AudienceMode.HOLD:
            self.window.slide.set_media_view()
            self.window.slide.image = self.last_image.copy()
            self.window.slide.set_blank("" if not self.last_image.isNull() else "black")
            if native:
                self.backend.set_blank("pause")
            self._cover(True)
        else:
            self.window.slide.set_media_view()
            image = QImage(1920, 1080, QImage.Format.Format_RGB32)
            image.fill(QColor("#10141C"))
            painter = QPainter(image)
            painter.setPen(QColor("#F4F2FF"))
            font = painter.font()
            font.setPixelSize(64)
            painter.setFont(font)
            painter.drawText(
                image.rect().adjusted(100, 100, -100, -100),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self.splash_text,
            )
            painter.end()
            self.window.slide.image = image
            self.window.slide.set_blank("")
            if native:
                self.backend.set_blank("pause")
            self._cover(True)
        self.window.slide.update()
        self.changed.emit(mode.value)

    def set_raster(self, page: int, raster) -> None:
        if not self.handoff and self.mode == AudienceMode.SLIDE:
            self.window.slide.set_raster(page, raster)
            self.last_image = self.window.slide.image.copy()

    def stop(self) -> None:
        self.handoff = False
        self.native_hwnd = 0
        self._cover(False)
        self.window.hide()
        self.visible = False
