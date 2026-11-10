from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSpinBox, QWidget

from pdf_presenter.i18n import tr


class ScaleControls(QWidget):
    changed = Signal(str, int)

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(tr("МАСШТАБ"))
        label.setObjectName("eyebrow")
        layout.addWidget(label)
        self.mode = QComboBox()
        for text, value in (
            (tr("Вписать"), "fit"),
            (tr("Заполнить"), "fill"),
            (tr("Растянуть"), "stretch"),
            (tr("Исходный 1:1"), "actual"),
            (tr("Произвольный"), "zoom"),
        ):
            self.mode.addItem(text, value)
        self.mode.setAccessibleName(tr("Режим масштаба изображения или видео"))
        self.zoom = QSpinBox()
        self.zoom.setRange(1, 1000)
        self.zoom.setValue(100)
        self.zoom.setSuffix(" %")
        self.zoom.setKeyboardTracking(False)
        self.zoom.setAccessibleName(tr("Масштаб в процентах"))
        self.zoom.setMinimumWidth(83)
        self.mode.currentIndexChanged.connect(self._changed)
        self.zoom.valueChanged.connect(self._changed)
        layout.addWidget(self.mode, 1)
        layout.addWidget(self.zoom)
        self.hide()

    def set_settings(self, settings):
        with QSignalBlocker(self.mode), QSignalBlocker(self.zoom):
            self.mode.setCurrentIndex(max(0, self.mode.findData(settings.get("scale", "fit"))))
            self.zoom.setValue(settings.get("zoom", 100))
        self.zoom.setEnabled(self.mode.currentData() == "zoom")

    def _changed(self, *_):
        self.zoom.setEnabled(self.mode.currentData() == "zoom")
        self.changed.emit(self.mode.currentData(), self.zoom.value())
