"""Online Canva viewer rendered by WebView2, coordinated with the existing audience cover."""

import hashlib

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter

from pdf_presenter.i18n import tr

from ..core.canva_url import normalize_canva_url
from ..core.capability_model import BackendCapabilities, PresentationDocument
from ..core.render_service import Raster
from ..services.canva_service import CanvaService
from .base_backend import PresentationBackend


class CanvaBackend(PresentationBackend):
    kind = "canva"
    label = "Canva · онлайн"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = None
        self.native_hwnd = 0
        self._handle = 0
        self._preview = QImage()
        self._starting = False
        self._covered = False
        self._poller = QTimer(self)
        self._poller.setInterval(300)
        self._poller.timeout.connect(self._poll)

    def get_capabilities(self):
        return BackendCapabilities(
            video=True,
            video_controls=True,
            audio=True,
            animations=True,
            transitions=True,
            native_window=True,
        )

    @property
    def pending_count(self):
        return self.service.pending if self.service else 0

    def load(self, file_path, password=""):
        try:
            self.path = normalize_canva_url(file_path)
            self.service = CanvaService(self.path)
            self.service.received.connect(self._received)
        except Exception as exc:
            self.load_failed.emit("document", tr("Не удалось открыть Canva: ") + str(exc))

    def _received(self, method, value):
        if self.disposed:
            return
        if method == "error":
            self._poller.stop()
            self.service.close(force=True)
            self.active = self._starting = False
            self._hide()
            if self.document is None:
                self.load_failed.emit("document", str(value))
            else:
                self.failed.emit(str(value))
            return
        if method == "command_error":
            if value["method"] == "control":
                self.video_failed.emit(value["message"])
            else:
                self._poller.stop()
                self.service.close(force=True)
                self.active = self._starting = False
                self._hide()
                self.failed.emit(value["message"])
            return
        if method == "loaded":
            try:
                count = int(value.get("count", 0))
            except (TypeError, ValueError, OverflowError):
                count = 0
            if not 0 < count <= 2000 or not value.get("h264"):
                self.service.close(force=True)
                self.load_failed.emit(
                    "document",
                    tr("Canva не предоставила слайды или WebView2 не поддерживает видео."),
                )
                return
            self._handle = int(value["hwnd"])
            self.document = PresentationDocument(
                self.path,
                hashlib.sha256(self.path.encode()).hexdigest(),
                count,
                str(value.get("title") or "Canva"),
                ((1920.0, 1080.0),) * count,
                warnings=(
                    tr(
                        "Canva работает через интернет. Предпросмотр следующего слайда недоступен; заметки хранятся в «Сцене»."
                    ),
                ),
            )
            self.loaded.emit(self.document)
            return
        if not isinstance(value, dict) or not value.get("ready") or not self.document:
            return
        try:
            current = int(value.get("index", self.current))
        except (TypeError, ValueError, OverflowError):
            self._received(
                "error", tr("Canva не передала номер текущего слайда. Откройте ссылку повторно.")
            )
            return
        if 0 <= current < self.document.page_count and current != self.current:
            self.current = current
            self._preview = QImage()
            self.position_changed.emit(current)
        videos = [
            dict(video, name=tr("Видео {number}", number=video["id"]))
            for video in value.get("videos", [])
        ]
        self.video_state_changed.emit(self.current, videos)
        if self.active and not self._covered and value.get("preview"):
            image = QImage.fromData(value["preview"])
            if not image.isNull():
                self._preview = image.scaled(
                    960,
                    600,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.frame_ready.emit(self._preview)
        if method == "start" and self._starting:
            self._starting = False
            self.active = True
            self.native_hwnd = self._handle
            self.native_window_changed.emit(self.native_hwnd)
            self._poller.start()
            self.started.emit()
        elif method == "stop":
            self.stopped.emit()

    def _poll(self):
        if not self.active or self.disposed:
            return
        if not self.service.pending:
            self.service.send("state", preview=not self._covered)

    def start(self, slide_index):
        if not self.document or not self.target or self.disposed:
            return
        if not self.service or self.service.closing:
            raise RuntimeError(tr("Окно Canva закрыто. Откройте ссылку повторно."))
        from ..services.native_window import position_window

        position_window(self._handle, self.target)
        self._starting = True
        self._covered = False
        self.service.send("start", index=slide_index, volume=self.media_settings.get("volume"))

    def _hide(self):
        import win32con
        import win32gui
        import win32process

        if (
            self._handle
            and win32gui.IsWindow(self._handle)
            and self.service
            and win32process.GetWindowThreadProcessId(self._handle)[1] == self.service.process.pid
        ):
            win32gui.ShowWindow(self._handle, win32con.SW_HIDE)
        self.native_hwnd = 0
        self.native_window_changed.emit(0)

    def stop(self):
        starting = self._starting
        self.active = self._starting = False
        self._poller.stop()
        self._hide()
        if starting and self.service:
            self.service.close(force=True)
            self._handle = 0
            self.stopped.emit()
            return
        if self.service and not self.service.closing:
            self.service.send("stop")
        else:
            self.stopped.emit()

    def set_display_target(self, target):
        super().set_display_target(target)
        if self.active:
            from ..services.native_window import position_window

            position_window(self._handle, target)

    def set_blank(self, color):
        if self.active or self._starting:
            self._covered = bool(color)
            self.service.send("cover", covered=bool(color))

    def next(self):
        if self.current + 1 >= self.get_slide_count():
            self.ended.emit()
            return False
        return self._navigate("next")

    def previous(self):
        return self._navigate("previous") if self.current > 0 else False

    def go_to_slide(self, index):
        if not self.document or not 0 <= index < self.get_slide_count() or self.disposed:
            return False
        if self.active:
            return self._navigate("goto", index)
        self.current = index
        self.position_changed.emit(index)
        return True

    def _navigate(self, action, index=0):
        if self.active and not self.disposed:
            self.service.send("navigate", action=action, index=index)
            return True
        if self.document:
            return self.go_to_slide(self.current + (1 if action == "next" else -1))
        return False

    def control_video(self, action, shape_id, *, slide_index, value=0):
        if not self.active or self._covered or self.disposed or slide_index != self.current:
            return False
        self.service.send("control", id=shape_id, action=action, value=value)
        return True

    def begin_frame(self):
        pass

    def request(self, tag, page, width, height, priority=0):
        if not self.document or self.disposed or not 0 <= page < self.get_slide_count():
            return
        if page == self.current and not self._preview.isNull():
            image = self._preview.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio)
        else:
            image = QImage(min(width, 1280), min(height, 720), QImage.Format.Format_RGB888)
            image.fill(QColor("#111827"))
            painter = QPainter(image)
            painter.setPen(QColor("#BAC8E6"))
            painter.drawText(
                image.rect(),
                Qt.AlignmentFlag.AlignCenter,
                tr("Canva · слайд {p0}\n", p0=page + 1)
                + (
                    tr("Начните показ")
                    if page == self.current
                    else tr("Предпросмотр во время показа")
                ),
            )
            painter.end()
        image = image.convertToFormat(QImage.Format.Format_RGB888)
        self.ready.emit(
            tag,
            page,
            Raster(image.width(), image.height(), image.bytesPerLine(), bytes(image.bits())),
        )

    def dispose(self):
        if self.disposed:
            return
        self._hide()
        self.disposed = True
        self.active = self._starting = False
        self._poller.stop()
        if self.service:
            try:
                self.service.received.disconnect(self._received)
            except RuntimeError:
                pass  # A failed helper may already have released its Qt service.
            self.service.close()

    close = dispose
