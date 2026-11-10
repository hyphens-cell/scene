from __future__ import annotations

from pathlib import Path
from typing import Any

from pdf_presenter.i18n import tr

from .canva_url import is_canva_url, normalize_canva_url
from .storage import StorageError, atomic_json, data_directory, read_json


class SettingsManager:
    def __init__(self, root: Path | None = None) -> None:
        self.path = (root or data_directory()) / "settings.json"
        self.values: dict[str, Any] = {}
        self.warning: str | None = None
        self.read_only = False
        try:
            data, self.warning = read_json(self.path, self._valid)
            if data:
                self.values = data["settings"]
        except StorageError as exc:
            self.warning = str(exc)
            self.read_only = True

    @staticmethod
    def _valid(data: object) -> bool:
        if not (
            isinstance(data, dict)
            and data.get("version") == 1
            and isinstance(data.get("settings"), dict)
        ):
            return False
        values = data["settings"]
        recent = values.get("recent_files", [])
        return (
            isinstance(recent, list)
            and values.get("language", "ru") in ("ru", "en")
            and all(isinstance(x, str) for x in recent)
            and isinstance(values.get("notes_font", 16), int)
            and 10 <= values.get("notes_font", 16) <= 40
            and all(
                isinstance(values.get(key, ""), str)
                for key in ("audience_monitor", "geometry", "main_splitter", "side_splitter")
            )
        )

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value

    def add_recent(self, path: Path | str) -> None:
        normalized = (
            normalize_canva_url(str(path)) if is_canva_url(str(path)) else str(Path(path).resolve())
        )
        recent = [x for x in self.get("recent_files", []) if x.casefold() != normalized.casefold()]
        self.values["recent_files"] = [normalized, *recent][:10]

    def save(self) -> None:
        if self.read_only:
            raise StorageError(
                tr("Настройки повреждены: исходные файлы сохранены, запись отключена.")
            )
        atomic_json(self.path, {"version": 1, "settings": self.values}, self._valid)
