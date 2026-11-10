from __future__ import annotations

import re
from pathlib import Path

from .storage import atomic_json, data_directory, read_json


class NotesManager:
    def __init__(self, fingerprint: str, root: Path | None = None) -> None:
        if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            raise ValueError("Invalid SHA-256 fingerprint")
        self.fingerprint = fingerprint
        self.path = (root or data_directory()) / "notes" / f"{fingerprint}.json"
        self.notes: dict[str, str] = {}
        self.dirty = False
        data, self.warning = read_json(self.path, self._valid)
        if data:
            self.notes = data["notes"]

    def _valid(self, data: object) -> bool:
        return (
            isinstance(data, dict)
            and data.get("version") == 1
            and data.get("document_sha256") == self.fingerprint
            and isinstance(data.get("notes"), dict)
            and all(
                isinstance(key, str)
                and key.isdecimal()
                and int(key) >= 0
                and isinstance(value, str)
                for key, value in data["notes"].items()
            )
        )

    def get(self, page: int) -> str:
        return self.notes.get(str(page), "")

    def set(self, page: int, text: str) -> None:
        if page < 0:
            raise ValueError("Negative page")
        if self.get(page) != text:
            if text:
                self.notes[str(page)] = text
            else:
                self.notes.pop(str(page), None)
            self.dirty = True

    def save(self) -> None:
        if self.dirty:
            atomic_json(
                self.path,
                {
                    "version": 1,
                    "document_sha256": self.fingerprint,
                    "notes": self.notes,
                },
                self._valid,
            )
            self.dirty = False
