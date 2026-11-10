from collections import OrderedDict

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from pdf_presenter.i18n import tr

from ..core.render_service import Raster
from .slide_widget import raster_image


class ThumbnailPanel(QWidget):
    selected = Signal(int)
    visible_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(160)
        layout = QVBoxLayout(self)
        heading = QLabel(tr("СЛАЙДЫ"))
        heading.setObjectName("muted")
        layout.addWidget(heading)
        self.list = QListWidget()
        self.list.setAccessibleName(tr("Миниатюры слайдов"))
        self.list.setViewMode(QListWidget.ViewMode.IconMode)
        self.list.setFlow(QListWidget.Flow.TopToBottom)
        self.list.setWrapping(False)
        self.list.setMovement(QListWidget.Movement.Static)
        self.list.setIconSize(QSize(150, 94))
        self.list.setGridSize(QSize(174, 128))
        self.list.setUniformItemSizes(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.currentRowChanged.connect(self.selected.emit)
        self.list.verticalScrollBar().valueChanged.connect(lambda _: self.visible_changed.emit())
        layout.addWidget(self.list)
        self._icons: OrderedDict[int, None] = OrderedDict()

    def set_document(self, count: int) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        self._icons.clear()
        for page in range(count):
            item = QListWidgetItem(f"{page + 1:02}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setSizeHint(QSize(174, 128))
            self.list.addItem(item)
        self.list.blockSignals(False)
        QTimer.singleShot(0, self.visible_changed.emit)

    def set_current(self, page: int) -> None:
        self.list.blockSignals(True)
        self.list.setCurrentRow(page)
        item = self.list.item(page)
        if item:
            self.list.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
        self.list.blockSignals(False)

    def visible_pages(self) -> list[int]:
        viewport = self.list.viewport().rect().adjusted(0, -128, 0, 128)
        return [
            page
            for page in range(self.list.count())
            if self.list.visualItemRect(self.list.item(page)).intersects(viewport)
        ]

    def set_raster(self, page: int, raster: Raster) -> None:
        item = self.list.item(page)
        if item is None:
            return
        item.setIcon(QIcon(QPixmap.fromImage(raster_image(raster))))
        self._icons[page] = None
        self._icons.move_to_end(page)
        while len(self._icons) > 60:
            removed, _ = self._icons.popitem(last=False)
            self.list.item(removed).setIcon(QIcon())

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._ensure_current_visible)
        self.visible_changed.emit()

    def _ensure_current_visible(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self.list.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
