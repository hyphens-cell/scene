from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from pdf_presenter.i18n import tr

from .icons import icon
from .media_controls import MediaControls
from .scale_controls import ScaleControls


class NavigationPanel(QWidget):
    go_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("navigation")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        self.slide_controls = QWidget()
        slide_layout = QVBoxLayout(self.slide_controls)
        slide_layout.setContentsMargins(0, 0, 0, 0)
        layout = QHBoxLayout()
        slide_layout.addLayout(layout)
        outer.addWidget(self.slide_controls)
        self.previous = QPushButton(tr("Назад"))
        self.previous.setIcon(icon("left"))
        self.next = QPushButton(tr("Вперёд"))
        self.next.setIcon(icon("right"))
        self.counter = QLabel("— / —")
        self.counter.setObjectName("counter")
        self.counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counter.setMinimumWidth(72)
        layout.addWidget(self.previous)
        layout.addWidget(self.counter)
        layout.addWidget(self.next)
        layout.addStretch()
        jump_layout = QHBoxLayout()
        slide_layout.addLayout(jump_layout)
        jump_layout.addWidget(QLabel(tr("Перейти к слайду")))
        self.jump = QSpinBox()
        self.jump.setRange(1, 1)
        self.jump.setKeyboardTracking(False)
        self.jump.setMinimumWidth(72)
        self.jump.setAccessibleName(tr("Перейти к слайду"))
        jump_layout.addWidget(self.jump)
        self.go = QPushButton(tr("Перейти"))
        self.go.clicked.connect(self.submit)
        jump_layout.addWidget(self.go)
        jump_layout.addStretch()
        self.media = MediaControls()
        self.media.hide()
        self.scale = ScaleControls()
        self.play_video = self.media.play
        outer.addWidget(self.media)
        outer.addWidget(self.scale)
        self.setEnabled(False)

    def set_content_kind(self, kind: str) -> None:
        self.slide_controls.setVisible(kind not in {"image", "video", "empty"})

    def submit(self) -> None:
        self.jump.interpretText()
        self.go_requested.emit(self.jump.value())

    def update_state(self, current: int, count: int) -> None:
        self.setEnabled(count > 0)
        self.counter.setText(f"{current + 1:02} / {count:02}" if count else "— / —")
        self.jump.setMaximum(max(1, count))
        self.jump.setValue(current + 1)
        self.previous.setEnabled(current > 0)
        self.next.setEnabled(current < count - 1)
