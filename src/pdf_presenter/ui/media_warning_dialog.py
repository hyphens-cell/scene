from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout

from pdf_presenter.i18n import tr


class MediaWarningDialog(QDialog):
    def __init__(self, title: str, warnings: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Проверка совместимости"))
        self.resize(650, 400)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText("\n\n".join(warnings) or tr("Предупреждений нет."))
        layout.addWidget(details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
