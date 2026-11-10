"""Read PPTX metadata without launching playback or following remote links."""

from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from pdf_presenter.i18n import tr


@dataclass
class MediaReport:
    embedded: list[str] = field(default_factory=list)
    linked: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    animations: bool = False
    transitions: bool = False


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    info = archive.getinfo(name)
    if info.file_size > 8 * 1024 * 1024:
        raise ValueError(
            tr("XML-часть PPTX слишком велика для безопасной предварительной проверки.")
        )
    with archive.open(info) as stream:
        data = stream.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024 or b"<!DOCTYPE" in data.upper():
        raise ValueError(tr("Недопустимая XML-часть PPTX."))
    return ET.fromstring(data)


def inspect_media(filename: str) -> MediaReport:
    path = Path(filename).resolve()
    report = MediaReport()
    if path.suffix.lower() == ".pdf":
        return report
    if path.suffix.lower() == ".ppt":
        report.warnings.append(
            tr(
                "Медиа старого формата PPT проверяются через установленный движок; полная проверка связей недоступна."
            )
        )
        return report
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) > 30000:
                raise ValueError(tr("Слишком много частей PPTX для предварительной проверки."))
            # Only metadata is read; embedded videos are never decompressed into memory.
            media_extensions = {
                ".mp4",
                ".m4v",
                ".mov",
                ".avi",
                ".wmv",
                ".mpg",
                ".mpeg",
                ".mp3",
                ".m4a",
                ".wav",
                ".wma",
                ".aac",
                ".ogg",
                ".webm",
            }
            report.embedded = [
                name
                for name in names
                if name.startswith("ppt/media/") and Path(name).suffix.lower() in media_extensions
            ]
            metadata_size = 0
            for name in names:
                is_slide = bool(re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
                is_relationship = name.startswith("ppt/slides/_rels/") and name.endswith(".rels")
                if not (is_slide or is_relationship):
                    continue
                metadata_size += archive.getinfo(name).file_size
                if metadata_size > 64 * 1024 * 1024:
                    raise ValueError(
                        tr("Метаданные PPTX превышают лимит предварительной проверки.")
                    )
                root = _xml(archive, name)
                if is_slide:
                    report.animations |= any(
                        element.tag.endswith("}timing") for element in root.iter()
                    )
                    report.transitions |= any(
                        element.tag.endswith("}transition") for element in root.iter()
                    )
                else:
                    for relation in root:
                        media_type = relation.get("Type", "").rsplit("/", 1)[-1]
                        if media_type not in {
                            "audio",
                            "video",
                            "media",
                        }:
                            continue
                        target = unquote(relation.get("Target", ""))
                        if relation.get("TargetMode") != "External":
                            internal = posixpath.normpath(posixpath.join("ppt/slides", target))
                            if internal not in report.embedded:
                                report.embedded.append(internal)
                                if internal not in names:
                                    report.warnings.append(
                                        tr(
                                            "Встроенный медиафайл отсутствует в PPTX: {p0}",
                                            p0=internal,
                                        )
                                    )
                            continue
                        if target in report.linked:
                            continue
                        report.linked.append(target)
                        parsed = urlsplit(target)
                        windows_path = bool(re.match(r"^[A-Za-z]:[\\/]", target))
                        if parsed.scheme not in ("", "file") and not windows_path:
                            report.warnings.append(
                                tr("Сетевой ресурс не проверялся офлайн: {p0}", p0=target)
                            )
                            continue
                        local = target
                        if parsed.scheme == "file":
                            local = unquote(parsed.path)
                            if re.match(r"^/[A-Za-z]:", local):
                                local = local[1:]
                            if parsed.netloc:
                                local = "//" + parsed.netloc + local
                        if local.startswith(("\\\\", "//")):
                            report.warnings.append(
                                tr("Сетевая папка не проверялась офлайн: {p0}", p0=target)
                            )
                            continue
                        resource = Path(local)
                        if not resource.is_absolute():
                            resource = path.parent / resource
                        if not resource.is_file():
                            report.missing.append(target)
            report.warnings.extend(
                tr("Не найден связанный медиафайл: {p0}", p0=value) for value in report.missing
            )
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError, OSError) as exc:
        report.warnings.append(
            tr("Не удалось полностью проверить медиа {p0}: {p1}", p0=path.name, p1=exc)
        )
    return report
