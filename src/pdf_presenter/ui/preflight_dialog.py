from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from pdf_presenter.i18n import tr

from ..core.presentation_queue import STATE_LABELS


class PreflightDialog(QDialog):
    def __init__(self, queue, monitor_count: int, parent=None) -> None:
        super().__init__(parent)
        self.queue = queue
        self.setWindowTitle(tr("Готовность мероприятия"))
        self.resize(900, 520)
        layout = QVBoxLayout(self)
        text = tr("Проверка не запускает показ или видео.")
        if monitor_count < 2:
            text += tr(" Второй монитор не обнаружен; доступен оконный предпросмотр.")
        self.summary = QLabel(text)
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            [tr("Презентация"), tr("Состояние"), tr("Слайды / движок"), tr("Предупреждения")]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        queue.item_changed.connect(self.refresh)
        queue.changed.connect(self.refresh)
        self.refresh()

    def refresh(self, *args) -> None:
        self.table.setRowCount(len(self.queue.items))
        for row, item in enumerate(self.queue.items):
            values = [
                item.name,
                tr(STATE_LABELS[item.state]),
                f"{item.slide_count or '—'} / {item.backend or '—'}",
                "\n".join(([item.error] if item.error else []) + item.warnings),
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                self.table.setItem(row, column, cell)
        self.table.resizeRowsToContents()
