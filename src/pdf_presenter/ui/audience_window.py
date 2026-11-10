from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QScreen
from PySide6.QtWidgets import QMainWindow

from pdf_presenter.i18n import tr

from .slide_widget import SlideWidget


class AudienceWindow(QMainWindow):
    closed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(tr("Сцена — предпросмотр аудитории"))
        self.slide = SlideWidget(audience=True)
        self.setCentralWidget(self.slide)
        self.setStyleSheet("background: black;")
        self.setMouseTracking(True)
        self.slide.setMouseTracking(True)
        self.slide.installEventFilter(self)
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.setInterval(1600)
        self._cursor_timer.timeout.connect(lambda: self.setCursor(Qt.CursorShape.BlankCursor))
        self.preview = True

    def display_on(self, screen: QScreen, preview: bool) -> None:
        self.preview = preview
        self.hide()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, not preview)
        self.winId()
        self.windowHandle().setScreen(screen)
        area = screen.availableGeometry() if preview else screen.geometry()
        if preview:
            width, height = min(800, area.width() * 2 // 3), min(500, area.height() * 2 // 3)
            self.setGeometry(area.right() - width - 24, area.bottom() - height - 24, width, height)
            self.showNormal()
        else:
            self.setGeometry(area)
            # QWidget defers geometry updates while hidden. On Windows the
            # fullscreen transition uses the native window's old rectangle.
            self.windowHandle().setGeometry(area)
            self.showFullScreen()
        self._cursor_timer.start()

    def eventFilter(self, watched: object, event: object) -> bool:
        from PySide6.QtCore import QEvent

        if event.type() == QEvent.Type.MouseMove:
            self.unsetCursor()
            self._cursor_timer.start()
        return super().eventFilter(watched, event)

    def closeEvent(self, event: object) -> None:
        self._cursor_timer.stop()
        self.closed.emit()
        event.accept()
