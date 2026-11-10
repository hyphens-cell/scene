from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QWidget

from pdf_presenter.i18n import tr

from ..core.media_layout import media_rect


class VideoSurface(QWidget):
    closed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("Сцена — видео аудитории"))
        self.setStyleSheet("background: black")
        self.setCursor(Qt.CursorShape.BlankCursor)
        self.video = QVideoWidget(self)
        self.video.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)
        self.video.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.source_size = (1280, 720)
        self.settings = {}

    def set_media_view(self, source, settings):
        self.source_size, self.settings = source, dict(settings)
        self._layout_video()

    def _layout_video(self):
        rect = media_rect(
            QRectF(self.rect()), self.source_size, self.settings, self.devicePixelRatioF()
        )
        self.video.setGeometry(rect.toAlignedRect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_video()

    def closeEvent(self, event):
        self.closed.emit()
        event.accept()
