from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from .canva_url import is_canva_url, normalize_canva_url
from .media_formats import SUPPORTED


class QueueState(StrEnum):
    WAITING = "waiting"
    CHECKING = "checking"
    PREPARING = "preparing"
    READY = "ready"
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


STATE_LABELS = {
    QueueState.WAITING: "Ожидает загрузки",
    QueueState.CHECKING: "Проверяется",
    QueueState.PREPARING: "Подготавливается",
    QueueState.READY: "Готова",
    QueueState.ACTIVE: "Активна",
    QueueState.COMPLETED: "Завершена",
    QueueState.ERROR: "Ошибка",
}


@dataclass
class PresentationItem:
    path: str
    id: str = field(default_factory=lambda: uuid4().hex)
    preferred_backend: str = "auto"
    last_slide: int = 0
    slide_count: int | None = None
    state: QueueState = QueueState.WAITING
    backend: str = ""
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    notes_ref: str = ""
    media_settings: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        if is_canva_url(self.path):
            return (
                "Canva · "
                + self.path.rstrip("/").split("/")[-2 if self.path.endswith("/view") else -1]
            )
        return Path(self.path).name

    @property
    def format(self) -> str:
        if is_canva_url(self.path):
            return "CANVA"
        return Path(self.path).suffix.lstrip(".").upper()


class PresentationQueueManager(QObject):
    changed = Signal()
    item_changed = Signal(str)
    active_changed = Signal(str)
    SUPPORTED = SUPPORTED

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.items: list[PresentationItem] = []
        self.active_id = ""

    def get(self, item_id: str) -> PresentationItem | None:
        return next((item for item in self.items if item.id == item_id), None)

    @property
    def active(self) -> PresentationItem | None:
        return self.get(self.active_id)

    def add(self, paths, preference: str = "auto") -> list[PresentationItem]:
        added = []
        for name in paths:
            if is_canva_url(str(name)):
                item = PresentationItem(normalize_canva_url(str(name)))
                self.items.append(item)
                added.append(item)
                continue
            path = Path(name).resolve()
            if path.suffix.lower() not in self.SUPPORTED:
                continue
            item = PresentationItem(str(path), preferred_backend=preference)
            self.items.append(item)
            added.append(item)
        if added:
            self.changed.emit()
        return added

    def add_folder(self, folder: str, preference: str = "auto") -> list[PresentationItem]:
        return self.add(
            sorted(
                (p for p in Path(folder).iterdir() if p.is_file()), key=lambda p: p.name.casefold()
            ),
            preference,
        )

    def remove(self, item_id: str) -> bool:
        if item_id == self.active_id:
            return False
        item = self.get(item_id)
        if item is None:
            return False
        self.items.remove(item)
        self.changed.emit()
        return True

    def move(self, item_id: str, index: int) -> bool:
        item = self.get(item_id)
        if item is None or not 0 <= index < len(self.items):
            return False
        self.items.remove(item)
        self.items.insert(index, item)
        self.changed.emit()
        return True

    def update(self, item_id: str, **values) -> None:
        item = self.get(item_id)
        if item is None:
            return
        for key, value in values.items():
            if key not in {
                "state",
                "last_slide",
                "slide_count",
                "backend",
                "warnings",
                "error",
                "notes_ref",
                "preferred_backend",
                "media_settings",
            }:
                raise ValueError(f"Unknown queue field: {key}")
            setattr(item, key, value)
        self.item_changed.emit(item_id)

    def activate(self, item_id: str) -> None:
        item = self.get(item_id)
        if item is None:
            raise KeyError(item_id)
        if self.active and self.active.id != item_id:
            self.update(self.active.id, state=QueueState.COMPLETED)
        self.active_id = item_id
        self.update(item_id, state=QueueState.ACTIVE, error="")
        self.active_changed.emit(item_id)

    def adjacent(self, direction: int, item_id: str | None = None) -> PresentationItem | None:
        current = self.get(item_id or self.active_id)
        if current is None:
            return self.items[0] if self.items and direction > 0 else None
        index = self.items.index(current) + direction
        return self.items[index] if 0 <= index < len(self.items) else None

    def replace(self, items: list[PresentationItem]) -> None:
        if len({item.id for item in items}) != len(items):
            raise ValueError("Duplicate queue identifiers")
        self.items = list(items)
        self.active_id = ""
        self.changed.emit()
