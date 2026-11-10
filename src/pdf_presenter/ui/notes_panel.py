from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pdf_presenter.i18n import tr


class NotesPanel(QWidget):
    edited = Signal(str)
    save_requested = Signal()

    def __init__(self, font_size: int = 16) -> None:
        super().__init__()
        self.setObjectName("panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self.heading = QLabel(tr("ЗАМЕТКИ"))
        self.heading.setObjectName("eyebrow")
        header.addWidget(self.heading)
        header.addStretch()
        self.font_size = QSpinBox()
        self.font_size.setRange(10, 40)
        self.font_size.setValue(font_size)
        self.font_size.setSuffix(" pt")
        self.font_size.setAccessibleName(tr("Размер шрифта заметок"))
        header.addWidget(self.font_size)
        layout.addLayout(header)
        privacy = QLabel(tr("Видны только вам"))
        privacy.setObjectName("muted")
        layout.addWidget(privacy)
        self.editor = QPlainTextEdit()
        self.editor.setAccessibleName(tr("Заметки докладчика"))
        self.editor.setPlaceholderText(tr("Ваши заметки к слайду. Их видите только вы."))
        self.editor.setTabChangesFocus(False)
        layout.addWidget(self.editor)
        footer = QHBoxLayout()
        self.status = QLabel(tr("Автосохранение"))
        self.status.setObjectName("muted")
        footer.addWidget(self.status)
        footer.addStretch()
        save = QPushButton(tr("Сохранить"))
        save.setObjectName("quiet")
        save.setToolTip(tr("Сохранить заметки · Ctrl+S"))
        save.clicked.connect(self.save_requested.emit)
        footer.addWidget(save)
        layout.addLayout(footer)
        self.font_size.valueChanged.connect(self._font_changed)
        self._font_changed(font_size)
        self.editor.textChanged.connect(lambda: self.edited.emit(self.editor.toPlainText()))
        self.setEnabled(False)

    def _font_changed(self, size: int) -> None:
        font = self.editor.font()
        font.setPointSize(size)
        self.editor.setFont(font)

    def set_note(self, page: int, text: str) -> None:
        self.heading.setText(tr("ЗАМЕТКИ · {p0:02}", p0=page + 1))
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)
