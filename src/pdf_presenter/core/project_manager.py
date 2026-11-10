from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from pdf_presenter.i18n import tr

from .backend_manager import BackendManager
from .canva_url import is_canva_url, normalize_canva_url
from .media_layout import MODES
from .presentation_queue import PresentationItem
from .storage import StorageError, atomic_json, read_json


@dataclass
class EventProject:
    name: str = field(default_factory=lambda: tr("Новое мероприятие"))
    items: list[PresentationItem] = field(default_factory=list)
    show_settings: dict = field(default_factory=dict)
    monitor_settings: dict = field(default_factory=dict)
    auto_advance: bool = False
    path: Path | None = None


class ProjectManager:
    MAX_ITEMS = 2000

    @staticmethod
    def _valid(data: object) -> bool:
        if (
            not isinstance(data, dict)
            or data.get("version") != 1
            or data.get("type") != "pdfpresenter"
        ):
            return False
        if not isinstance(data.get("name"), str) or len(data["name"]) > 1000:
            return False
        if (
            not isinstance(data.get("presentations"), list)
            or len(data["presentations"]) > ProjectManager.MAX_ITEMS
        ):
            return False
        identifiers = set()
        for item in data["presentations"]:
            if not isinstance(item, dict):
                return False
            if (
                not isinstance(item.get("id"), str)
                or not re.fullmatch(r"[a-f0-9]{32}", item["id"])
                or item["id"] in identifiers
            ):
                return False
            identifiers.add(item["id"])
            if not isinstance(item.get("path"), str) or not item["path"] or "\0" in item["path"]:
                return False
            if "://" in item["path"] and not is_canva_url(item["path"]):
                return False
            if item.get("preferred_backend", "auto") not in BackendManager.PREFERENCES:
                return False
            slide = item.get("last_slide", 0)
            if type(slide) is not int or not 0 <= slide <= 1_000_000:
                return False
            reference = item.get("notes_ref", "")
            if not isinstance(reference, str) or (
                reference and not re.fullmatch(r"[a-f0-9]{64}", reference)
            ):
                return False
            media = item.get("media_settings", {})
            if (
                not isinstance(media, dict)
                or not isinstance(media.get("scale", "fit"), str)
                or media.get("scale", "fit") not in MODES
            ):
                return False
            if type(media.get("loop", False)) is not bool:
                return False
            if type(media.get("zoom", 100)) is not int or not 1 <= media.get("zoom", 100) <= 1000:
                return False
            if (
                type(media.get("volume", 100)) is not int
                or not 0 <= media.get("volume", 100) <= 100
            ):
                return False
            for key in ("pan_x", "pan_y"):
                value = media.get(key, 0)
                if (
                    type(value) not in (float, int)
                    or not math.isfinite(value)
                    or not -1 <= value <= 1
                ):
                    return False
        if not isinstance(data.get("show_settings", {}), dict) or not isinstance(
            data.get("monitor_settings", {}), dict
        ):
            return False
        show = data.get("show_settings", {})
        monitors = data.get("monitor_settings", {})
        return (
            type(data.get("auto_advance", False)) is bool
            and isinstance(show.get("splash_text", ""), str)
            and len(show.get("splash_text", "")) <= 10000
            and isinstance(monitors.get("audience_monitor", ""), str)
            and isinstance(monitors.get("presenter_monitor", ""), str)
        )

    @staticmethod
    def _portable_path(filename: str, directory: Path) -> str:
        if is_canva_url(filename):
            return normalize_canva_url(filename)
        path = Path(filename).resolve()
        try:
            return path.relative_to(directory).as_posix()
        except ValueError:
            return str(path)

    def save(self, project: EventProject, path: Path | None = None) -> Path:
        target = path or project.path
        if target is None:
            raise StorageError(tr("Выберите имя файла проекта."))
        target = Path(target).resolve()
        if target.suffix.lower() != ".pdfpresenter":
            target = target.with_suffix(".pdfpresenter")
        data = {
            "version": 1,
            "type": "pdfpresenter",
            "name": project.name,
            "presentations": [
                {
                    "id": item.id,
                    "path": self._portable_path(item.path, target.parent),
                    "preferred_backend": item.preferred_backend,
                    "last_slide": item.last_slide,
                    "notes_ref": item.notes_ref,
                    "media_settings": dict(item.media_settings),
                }
                for item in project.items
            ],
            "show_settings": project.show_settings,
            "monitor_settings": project.monitor_settings,
            "auto_advance": project.auto_advance,
        }
        if not self._valid(data):
            raise StorageError(tr("Параметры проекта имеют неверный формат."))
        atomic_json(target, data, self._valid)
        project.path = target
        return target

    def load(self, path: Path) -> tuple[EventProject, str | None]:
        path = Path(path).resolve()
        if not path.is_file():
            raise StorageError(tr("Файл проекта не найден."))
        if path.stat().st_size > 8 * 1024 * 1024:
            raise StorageError(
                tr("Файл проекта слишком большой; документы не должны храниться внутри JSON.")
            )
        data, warning = read_json(path, self._valid)
        if data is None:
            raise StorageError(tr("Проект пуст."))
        items = []
        for value in data["presentations"]:
            if is_canva_url(value["path"]):
                filename = normalize_canva_url(value["path"])
            else:
                local = Path(value["path"])
                if not local.is_absolute():
                    local = path.parent / local
                filename = str(local.resolve())
            items.append(
                PresentationItem(
                    path=str(filename),
                    id=value["id"],
                    preferred_backend=value.get("preferred_backend", "auto"),
                    last_slide=value.get("last_slide", 0),
                    notes_ref=value.get("notes_ref", ""),
                    media_settings=dict(value.get("media_settings", {})),
                )
            )
        return EventProject(
            data["name"],
            items,
            data.get("show_settings", {}),
            data.get("monitor_settings", {}),
            data.get("auto_advance", False),
            path,
        ), warning
