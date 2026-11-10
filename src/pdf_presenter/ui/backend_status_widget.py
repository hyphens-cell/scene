from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from pdf_presenter.i18n import tr

from ..core.capability_model import COMPATIBILITY_WARNING
from .elided_label import ElidedLabel


class BackendStatusWidget(QWidget):
    preference_changed = Signal(str)
    warnings_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        layout = QHBoxLayout()
        outer.addLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        self.status = ElidedLabel(tr("PDF готов к работе"))
        self.status.setObjectName("muted")
        layout.addWidget(self.status, 1)
        self.preference = QComboBox()
        self.preference.setAccessibleName(tr("Предпочтительный движок PowerPoint"))
        self.preference.setMaximumWidth(230)
        self.preference.setMinimumWidth(150)
        self.preference.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.preference.setMinimumContentsLength(12)
        for name, value in (
            (tr("Автоматически"), "auto"),
            ("Microsoft PowerPoint", "powerpoint"),
            (tr("LibreOffice Impress (экспериментально)"), "libreoffice"),
            ("LibreOffice → PDF", "libreoffice_pdf"),
            (tr("Готовая PDF-копия"), "pdf_copy"),
        ):
            self.preference.addItem(name, value)
        self.preference_label = QLabel(tr("Открывать PPT/PPTX"))
        self.preference_label.setObjectName("muted")
        layout.addWidget(self.preference_label)
        layout.addWidget(self.preference)
        self.warning_button = QPushButton(tr("Предупреждения"))
        self.warning_button.setObjectName("quiet")
        self.warning_button.clicked.connect(self.warnings_requested)
        self.warning_button.setEnabled(False)
        layout.addWidget(self.warning_button)
        self.preference.currentIndexChanged.connect(
            lambda _: self.preference_changed.emit(self.preference.currentData())
        )
        self.compatibility_notice = QLabel()
        self.compatibility_notice.setWordWrap(True)
        self.compatibility_notice.setObjectName("compatibilityWarning")
        self.compatibility_notice.hide()
        outer.addWidget(self.compatibility_notice)

    def set_backend(self, backend, warnings) -> None:
        capabilities = backend.get_capabilities()
        media = tr("нативные медиа и анимации") if capabilities.video else tr("статические слайды")
        if backend.kind == "video":
            media = tr("видео и звук · плеер докладчика")
        elif backend.kind == "image":
            media = tr("изображение · настройка масштаба")
        if capabilities.native_window and capabilities.compatibility:
            media = tr("экспериментальный показ · совместимость ограничена")
        self.status.setText(f"{backend.label} · {media}")
        self.status.setToolTip(self.status.text())
        self.compatibility_notice.setVisible(capabilities.compatibility)
        self.compatibility_notice.setText(
            tr(COMPATIBILITY_WARNING)
            if not capabilities.native_window
            else tr(
                "Режим LibreOffice: совместимость анимаций, переходов и медиа не гарантируется."
            )
        )
        self.warning_button.setEnabled(bool(warnings))
        self.warning_button.setText(
            tr("Предупреждения · {p0}", p0=len(warnings)) if warnings else tr("Предупреждения")
        )
