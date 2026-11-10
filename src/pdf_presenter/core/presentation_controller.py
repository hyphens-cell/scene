from PySide6.QtCore import QObject, Signal

from .presentation_timer import PresentationTimer
from .slide_controller import SlideController


class PresentationController(QObject):
    started = Signal()
    stopped = Signal()
    blank_changed = Signal(str)
    number_changed = Signal(str)
    invalid_number = Signal()

    def __init__(self, slides: SlideController, timer: PresentationTimer) -> None:
        super().__init__()
        self.slides, self.timer = slides, timer
        self.active = False
        self.blank = ""
        self.number = ""
        self.requested_start_index = 0

    def start(self, from_current: bool = False) -> bool:
        if not self.slides.count:
            return False
        self.cancel_number()
        self.set_blank("")
        self.requested_start_index = self.slides.current if from_current else 0
        if not from_current:
            self.slides.go_to(0)
        self.active = True
        self.timer.start()
        self.started.emit()
        return True

    def stop(self) -> None:
        self.cancel_number()
        self.timer.pause()
        self.active = False
        self.set_blank("")
        self.stopped.emit()

    def set_blank(self, color: str) -> None:
        if color not in ("", "black", "white"):
            raise ValueError("Unknown blank color")
        self.blank = color
        self.blank_changed.emit(color)

    def toggle_blank(self, color: str) -> None:
        if self.active:
            self.set_blank("" if self.blank == color else color)

    def digit(self, digit: str) -> None:
        if self.active and digit in "0123456789" and len(digit) == 1:
            self.number = (self.number + digit)[:6]
            self.number_changed.emit(self.number)

    def backspace(self) -> None:
        self.number = self.number[:-1]
        self.number_changed.emit(self.number)

    def cancel_number(self) -> None:
        self.number = ""
        self.number_changed.emit("")

    def submit_number(self) -> bool:
        if not self.number:
            return False
        valid = self.slides.go_to_number(int(self.number))
        if valid:
            self.cancel_number()
        else:
            self.invalid_number.emit()
        return valid

    def escape(self) -> None:
        if self.number:
            self.cancel_number()
        elif self.active:
            self.stop()
