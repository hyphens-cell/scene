from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtWidgets import QWidget


class MonitorManager(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        app = QGuiApplication.instance()
        app.screenAdded.connect(self._changed)
        app.screenRemoved.connect(self._changed)
        for screen in self.screens():
            self._connect_screen(screen)

    def _connect_screen(self, screen: QScreen) -> None:
        screen.geometryChanged.connect(self._changed)
        screen.logicalDotsPerInchChanged.connect(self._changed)

    def _changed(self, *args: object) -> None:
        if args and isinstance(args[0], QScreen) and args[0] in self.screens():
            self._connect_screen(args[0])
        # Let Qt finish removing a QScreen before touching any window handles.
        QTimer.singleShot(0, self.changed.emit)

    def screens(self) -> list[QScreen]:
        return QGuiApplication.screens()

    def resolve(self, name: str) -> QScreen | None:
        return next((screen for screen in self.screens() if screen.name() == name), None)

    def default_audience(self, presenter: QScreen | None) -> QScreen | None:
        return next((screen for screen in self.screens() if screen != presenter), presenter)

    def requires_preview(self, audience: QScreen, presenter: QScreen | None) -> bool:
        return len(self.screens()) < 2 or audience == presenter

    @staticmethod
    def move_presenter(widget: QWidget, screen: QScreen) -> None:
        widget.showNormal()
        widget.winId()
        widget.windowHandle().setScreen(screen)
        area = screen.availableGeometry()
        widget.resize(min(widget.width(), area.width()), min(widget.height(), area.height()))
        widget.move(
            area.x() + max(0, (area.width() - widget.width()) // 2),
            area.y() + max(0, (area.height() - widget.height()) // 2),
        )
