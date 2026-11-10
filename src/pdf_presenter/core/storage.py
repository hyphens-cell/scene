"""Versioned JSON with atomic replacement and a recoverable last-good backup."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pdf_presenter.i18n import tr


class StorageError(Exception):
    """Data could not be read or safely persisted."""


def data_directory() -> Path:
    base = os.environ.get("APPDATA")
    return (Path(base) if base else Path.home() / ".config") / "PDFPresenter"


def _replace_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path: Path, value: dict[str, Any], validate: Callable[[object], bool]) -> None:
    try:
        payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
        if path.exists():
            old = path.read_bytes()
            # Never replace a good backup with corrupt JSON.
            try:
                valid = validate(json.loads(old))
            except (ValueError, UnicodeError):
                pass
            else:
                if valid:
                    _replace_bytes(path.with_suffix(path.suffix + ".bak"), old)
        _replace_bytes(path, payload)
    except (OSError, ValueError, TypeError) as exc:
        raise StorageError(tr("Не удалось сохранить {p0}: {p1}", p0=path.name, p1=exc)) from exc


def read_json(
    path: Path, validate: Callable[[object], bool]
) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists() and not path.with_suffix(path.suffix + ".bak").exists():
        return None, None
    errors = []
    for candidate in (path, path.with_suffix(path.suffix + ".bak")):
        try:
            result = json.loads(candidate.read_text(encoding="utf-8"))
            if not validate(result):
                raise ValueError(tr("неподдерживаемый формат данных"))
            warning = tr("Восстановлена резервная копия {p0}.", p0=path.name) if errors else None
            return result, warning
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            errors.append(str(exc))
    raise StorageError(
        tr("Не удалось прочитать {p0}. Исходные файлы сохранены. ", p0=path.name) + errors[0]
    )
