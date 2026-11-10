from PySide6.QtCore import QObject, Signal


class SlideController(QObject):
    changed = Signal(int)
    document_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.count = 0
        self.current = 0
        self.backend = None

    def bind_backend(self, backend) -> None:
        if self.backend is not None:
            self.backend.position_changed.disconnect(self.sync_current)
        self.backend = backend
        if backend is not None:
            backend.position_changed.connect(self.sync_current)

    def sync_current(self, index: int) -> None:
        if 0 <= index < self.count and self.current != index:
            self.current = index
            self.changed.emit(index)

    def set_document(self, count: int) -> None:
        if count < 0:
            raise ValueError("Negative page count")
        self.count, self.current = count, 0
        self.document_changed.emit(count)
        self.changed.emit(0)

    def go_to(self, index: int) -> bool:
        if not 0 <= index < self.count:
            return False
        if self.backend is not None:
            if not self.backend.get_capabilities().arbitrary_jump:
                return False
            return self.backend.go_to_slide(index)
        if self.current != index:
            self.current = index
            self.changed.emit(index)
        return True

    def go_to_number(self, number: int) -> bool:
        return self.go_to(number - 1)

    def next(self) -> bool:
        if self.backend is not None:
            return self.backend.next()
        return self.go_to(self.current + 1)

    def previous(self) -> bool:
        if self.backend is not None:
            return self.backend.previous()
        return self.go_to(self.current - 1)
