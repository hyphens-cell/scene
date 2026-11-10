"""Application-level routing works from either window without stealing editor input."""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QSlider,
    QSpinBox,
    QTextEdit,
)


class KeyboardRouter(QObject):
    def __init__(self, presenter: object) -> None:
        super().__init__(presenter)
        self.window = presenter

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        if event.type() != QEvent.Type.KeyPress:
            return False
        assert isinstance(event, QKeyEvent)
        app = QApplication.instance()
        if app.activeModalWidget() is not None or app.activePopupWidget() is not None:
            return False
        focus = app.focusWidget()
        active = app.activeWindow()
        if active not in (self.window, self.window.audience):
            return False
        key, modifiers = event.key(), event.modifiers()
        editing = isinstance(
            focus, (QPlainTextEdit, QTextEdit, QLineEdit, QSpinBox, QComboBox, QSlider)
        )
        if focus is not None and self.window.navigation.media.isAncestorOf(focus):
            # Player keys stay local, while emergency display controls remain available.
            # A combo box still owns letters/Escape for selection and popup dismissal.
            if isinstance(focus, QComboBox) or key not in (
                Qt.Key.Key_Escape,
                Qt.Key.Key_B,
                Qt.Key.Key_W,
            ):
                return False
            editing = False
        if editing:
            if focus == self.window.navigation.jump or self.window.navigation.jump.isAncestorOf(
                focus
            ):
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self.window.navigation.submit()
                    return True
            return False
        if modifiers & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        ):
            return False
        show = self.window.presentation
        slides = self.window.slides
        if self.window.loading and key not in (Qt.Key.Key_Escape, Qt.Key.Key_B, Qt.Key.Key_W):
            return False
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Space, Qt.Key.Key_PageDown):
            slides.next()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp):
            slides.previous()
        elif key == Qt.Key.Key_Home:
            slides.go_to(0)
        elif key == Qt.Key.Key_End:
            slides.go_to(slides.count - 1)
        elif key == Qt.Key.Key_Escape:
            show.escape()
        elif key == Qt.Key.Key_B:
            show.toggle_blank("black")
        elif key == Qt.Key.Key_W:
            show.toggle_blank("white")
        elif key == Qt.Key.Key_Backspace and show.number:
            show.backspace()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and show.number:
            show.submit_number()
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9 and show.active:
            show.digit(str(key - Qt.Key.Key_0))
        else:
            return False
        return True
