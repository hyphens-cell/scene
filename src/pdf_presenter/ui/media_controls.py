from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from pdf_presenter.i18n import tr

from .icons import icon


def media_time(milliseconds: int) -> str:
    seconds = max(0, milliseconds) // 1000
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"


class MediaControls(QWidget):
    """Controls carry the slide/media identity captured from the last valid state."""

    command_requested = Signal(int, int, str, int)

    def __init__(self):
        super().__init__()
        self.index = -1
        self.videos = []
        self.available = False
        self.setObjectName("mediaControls")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        heading = QHBoxLayout()
        label = QLabel(tr("ПЛЕЕР"))
        label.setObjectName("eyebrow")
        heading.addWidget(label)
        self.choice = QComboBox()
        self.choice.setAccessibleName(tr("Выбрать видео"))
        self.choice.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.choice.setMinimumContentsLength(8)
        self.choice.currentIndexChanged.connect(self._refresh)
        self.choice.setMinimumWidth(0)
        heading.addWidget(self.choice, 1)
        layout.addLayout(heading)
        row = QHBoxLayout()
        self.play = QPushButton(tr("Пуск"))
        self.play.setObjectName("primary")
        self.play.setIcon(icon("play", "#FFFFFF"))
        self.play.setIconSize(QSize(18, 18))
        self.play.setMinimumWidth(75)
        self.stop = QPushButton(tr("Стоп"))
        self.stop.setIcon(icon("stop"))
        self.play.setAccessibleName(tr("Пуск или пауза видео"))
        self.stop.setAccessibleName(tr("Остановить видео"))
        self.play.clicked.connect(self._toggle)
        self.stop.clicked.connect(lambda: self._send("stop"))
        row.addWidget(self.play)
        row.addWidget(self.stop)
        self.repeat = QPushButton(tr("Повтор"))
        self.repeat.setIcon(icon("repeat"))
        self.repeat.setCheckable(True)
        self.repeat.setAccessibleName(tr("Повторять видео по кругу"))
        self.repeat.setToolTip(
            tr("Повторять этот ролик до остановки; не переходить к следующему материалу")
        )
        self.repeat.clicked.connect(lambda checked: self._send("loop", int(checked)))
        row.addWidget(self.repeat)
        row.addStretch()
        volume_icon = QLabel()
        volume_icon.setPixmap(icon("volume").pixmap(18, 18))
        volume_icon.setToolTip(tr("Громкость видео"))
        row.addWidget(volume_icon)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(100)
        self.volume.setMinimumWidth(55)
        self.volume.setMaximumWidth(100)
        self.volume.setTracking(False)
        self.volume.setAccessibleName(tr("Громкость видео"))
        self.volume.valueChanged.connect(lambda value: self._send("volume", value))
        row.addWidget(self.volume)
        self.volume_value = QLabel("100%")
        self.volume_value.setObjectName("muted")
        self.volume_value.setMinimumWidth(36)
        self.volume_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.volume.valueChanged.connect(lambda value: self.volume_value.setText(f"{value}%"))
        self.volume.sliderMoved.connect(lambda value: self.volume_value.setText(f"{value}%"))
        row.addWidget(self.volume_value)
        progress = QHBoxLayout()
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.setSingleStep(1000)
        self.seek.setPageStep(5000)
        self.seek.setTracking(False)
        self.seek.setAccessibleName(tr("Перемотка видео"))
        self.seek.setMinimumHeight(20)
        self.seek.valueChanged.connect(lambda value: self._send("seek", value))
        self.seek.sliderMoved.connect(self._show_time)
        self.time = QLabel("00:00 / 00:00")
        self.time.setObjectName("muted")
        progress.addWidget(self.seek, 1)
        progress.addWidget(self.time)
        layout.addLayout(progress)
        layout.addLayout(row)
        self.reset()

    @property
    def selected(self):
        identifier = self.choice.currentData()
        return next((video for video in self.videos if video["id"] == identifier), None)

    def reset(self, index=-1):
        self.index, self.videos = index, []
        with QSignalBlocker(self.choice):
            self.choice.clear()
            self.choice.addItem(tr("Видео не выбрано"), 0)
        self._refresh()

    def set_available(self, available: bool):
        if self.available != available:
            self.available = available
            self._refresh()

    def update_state(self, index: int, videos: list[dict]):
        old = self.choice.currentData() if index == self.index else None
        previous = [(v["id"], v["name"]) for v in self.videos]
        self.index, self.videos = index, videos
        if previous != [(v["id"], v["name"]) for v in videos] or self.choice.currentData() == 0:
            with QSignalBlocker(self.choice):
                self.choice.clear()
                for video in videos:
                    self.choice.addItem(video["name"], video["id"])
                if not videos:
                    self.choice.addItem(tr("На слайде нет видео"), 0)
                desired = self.choice.findData(old)
                if desired >= 0:
                    self.choice.setCurrentIndex(desired)
                else:
                    playing = next((v["id"] for v in videos if v["state"] == 0), None)
                    if playing is not None:
                        self.choice.setCurrentIndex(self.choice.findData(playing))
        self._refresh()

    def _refresh(self, *_):
        video = self.selected
        enabled = self.available and video is not None
        state = video["state"] if video else 3
        self.play.setText(tr("Пауза") if state == 0 else tr("Пуск"))
        self.play.setIcon(icon("pause" if state == 0 else "play", "#FFFFFF"))
        self.play.setEnabled(enabled)
        self.stop.setEnabled(enabled and state != 3)
        self.repeat.setEnabled(enabled and video.get("loop") is not None if video else False)
        with QSignalBlocker(self.repeat):
            self.repeat.setChecked(bool(video.get("loop")) if video else False)
        self.choice.setEnabled(self.available and len(self.videos) > 1)
        self.seek.setEnabled(enabled and bool(video.get("seekable")) if video else False)
        self.volume.setEnabled(enabled and video.get("volume") is not None if video else False)
        self.volume.setToolTip(
            tr("Громкость ролика")
            if self.volume.isEnabled()
            else tr("Регулировка громкости этого ролика недоступна")
        )
        with QSignalBlocker(self.seek):
            self.seek.setMaximum(int(video["duration"]) if video else 0)
            if not self.seek.isSliderDown():
                self.seek.setValue(int(video["position"]) if video else 0)
                self._show_time(self.seek.value())
        if video and video.get("volume") is not None and not self.volume.isSliderDown():
            with QSignalBlocker(self.volume):
                self.volume.setValue(int(video["volume"]))
            self.volume_value.setText(f"{int(video['volume'])}%")
        elif not video or video.get("volume") is None:
            self.volume_value.setText("—")
        self.volume_value.setToolTip(self.volume.toolTip())

    def _show_time(self, position: int):
        video = self.selected
        duration = int(video["duration"]) if video else 0
        self.time.setText(f"{media_time(position)} / {media_time(duration)}")

    def _toggle(self):
        video = self.selected
        if video:
            self._send("pause" if video["state"] == 0 else "play")

    def _send(self, action: str, value=0):
        video = self.selected
        if self.available and video:
            self.command_requested.emit(self.index, video["id"], action, int(value))
