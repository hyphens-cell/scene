from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pdf_presenter.i18n import tr

from ..core.media_formats import IMAGES, VIDEOS
from ..core.presentation_queue import QueueState
from .icons import icon
from .presentation_item_widget import presentation_item_text


class PresentationQueuePanel(QWidget):
    add_requested = Signal()
    folder_requested = Signal()
    canva_requested = Signal()
    open_requested = Signal(str)
    preflight_requested = Signal()
    remove_requested = Signal(str)
    move_requested = Signal(str, int)

    def __init__(self, queue, parent=None) -> None:
        super().__init__(parent)
        self.queue = queue
        self.setMinimumWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel(tr("ОЧЕРЕДЬ ПОКАЗА"))
        title.setObjectName("eyebrow")
        header.addWidget(title)
        header.addStretch()
        self.count = QLabel("0")
        self.count.setObjectName("muted")
        header.addWidget(self.count)
        layout.addLayout(header)
        row = QHBoxLayout()
        for text, glyph, signal in (
            (tr("Файлы"), "plus", self.add_requested),
            (tr("Папка"), "folder", self.folder_requested),
        ):
            button = QPushButton(text)
            button.setIcon(icon(glyph))
            button.clicked.connect(signal)
            row.addWidget(button)
        layout.addLayout(row)
        self.canva = QPushButton(tr("Ссылка Canva"))
        self.canva.setIcon(icon("link"))
        self.canva.setToolTip(tr("Добавить онлайн-презентацию Canva с анимациями и видео"))
        self.canva.clicked.connect(self.canva_requested)
        layout.addWidget(self.canva)
        self.list = QListWidget()
        self.list.setObjectName("materialList")
        self.list.setAccessibleName(tr("Очередь материалов"))
        self.list.setWordWrap(False)
        self.list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.list.setIconSize(QSize(25, 25))
        self.list.setSpacing(4)
        self.list.itemDoubleClicked.connect(
            lambda item: self.open_requested.emit(item.data(Qt.ItemDataRole.UserRole))
        )
        layout.addWidget(self.list, 1)
        self.empty = QLabel(
            tr("Добавьте презентации, картинки или видео.\nФайлы можно перетащить в окно.")
        )
        self.empty.setWordWrap(True)
        self.empty.setObjectName("muted")
        layout.addWidget(self.empty)
        row = QHBoxLayout()
        self.up = QPushButton()
        self.down = QPushButton()
        for button, glyph in ((self.up, "up"), (self.down, "down")):
            button.setIcon(icon(glyph))
            button.setObjectName("iconButton")
        self.remove = QPushButton(tr("Удалить"))
        self.up.setAccessibleName(tr("Переместить презентацию вверх"))
        self.down.setAccessibleName(tr("Переместить презентацию вниз"))
        self.up.setToolTip(self.up.accessibleName())
        self.down.setToolTip(self.down.accessibleName())
        self.remove.setObjectName("quiet")
        self.up.clicked.connect(lambda: self._move(-1))
        self.down.clicked.connect(lambda: self._move(1))
        self.remove.clicked.connect(lambda: self.remove_requested.emit(self.selected_id()))
        for button in (self.up, self.down, self.remove):
            row.addWidget(button)
        layout.addLayout(row)
        self.open = QPushButton(tr("Открыть материал"))
        self.open.setIcon(icon("right"))
        self.open.clicked.connect(lambda: self.open_requested.emit(self.selected_id()))
        layout.addWidget(self.open)
        check = QPushButton(tr("Проверить материалы"))
        check.setIcon(icon("check"))
        check.setObjectName("quiet")
        check.clicked.connect(self.preflight_requested)
        layout.addWidget(check)
        self.list.currentRowChanged.connect(self._buttons)
        queue.changed.connect(self.refresh)
        queue.item_changed.connect(lambda _: self.refresh())
        self.refresh()

    def selected_id(self) -> str:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def select(self, item_id: str) -> None:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.ItemDataRole.UserRole) == item_id:
                self.list.setCurrentRow(row)
                break

    def refresh(self) -> None:
        selected = self.selected_id()
        self.list.blockSignals(True)
        self.list.clear()
        for value in self.queue.items:
            item = QListWidgetItem(presentation_item_text(value))
            suffix = "." + value.format.lower()
            glyph, color = (
                ("link", "#6CD6D5")
                if value.format == "CANVA"
                else ("play", "#B79DFF")
                if suffix in VIDEOS
                else ("image", "#6CD6D5")
                if suffix in IMAGES
                else ("slides", "#EDB888")
                if suffix in {".ppt", ".pptx"}
                else ("document", "#B2BDDB")
            )
            item.setIcon(icon(glyph, color))
            item.setSizeHint(QSize(0, 84))
            item.setData(Qt.ItemDataRole.UserRole, value.id)
            item.setToolTip("\n".join([value.path, value.error, *value.warnings]))
            if value.state == QueueState.ERROR:
                item.setForeground(QColor("#FF9EAA"))
            elif value.state == QueueState.ACTIVE:
                item.setForeground(QColor("#C9AAFF"))
            self.list.addItem(item)
        self.select(selected or self.queue.active_id)
        self.list.blockSignals(False)
        self.empty.setVisible(not self.queue.items)
        self.count.setText(str(len(self.queue.items)))
        self._buttons()

    def _buttons(self, *args) -> None:
        row = self.list.currentRow()
        self.up.setEnabled(row > 0)
        self.down.setEnabled(0 <= row < self.list.count() - 1)
        self.open.setEnabled(row >= 0)
        self.remove.setEnabled(row >= 0 and self.selected_id() != self.queue.active_id)

    def _move(self, direction: int) -> None:
        self.move_requested.emit(self.selected_id(), self.list.currentRow() + direction)
