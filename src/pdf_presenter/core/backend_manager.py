from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from pdf_presenter.i18n import tr

from .canva_url import is_canva_url, normalize_canva_url
from .capability_model import COMPATIBILITY_WARNING, BackendUnavailable
from .media_formats import IMAGES, VIDEOS


@dataclass(frozen=True)
class EngineAvailability:
    powerpoint: bool = False
    libreoffice: str = ""
    libreoffice_automation: bool = False


@dataclass(frozen=True)
class BackendChoice:
    kind: str
    path: str
    warning: str = ""


def _registered(progid: str) -> bool:
    if sys.platform != "win32" or importlib.util.find_spec("pythoncom") is None:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid + "\\CLSID"):
            return True
    except OSError:
        return False


def detect_engines() -> EngineAvailability:
    candidates = [shutil.which("soffice.com"), shutil.which("soffice.exe"), shutil.which("soffice")]
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        if root := os.environ.get(variable):
            candidates.extend(
                str(Path(root) / suffix / "program" / binary)
                for suffix in ("LibreOffice", "Programs/LibreOffice")
                for binary in ("soffice.com", "soffice.exe")
            )
    libreoffice = next((str(Path(p).resolve()) for p in candidates if p and Path(p).is_file()), "")
    return EngineAvailability(
        _registered("PowerPoint.Application"),
        libreoffice,
        _registered("com.sun.star.ServiceManager"),
    )


class BackendManager:
    """Detect candidates at startup; actual load/prepare validates their usability."""

    PREFERENCES = ("auto", "powerpoint", "libreoffice", "libreoffice_pdf", "pdf_copy")

    def __init__(self, availability: EngineAvailability | None = None, services=None) -> None:
        self.availability = availability if availability is not None else detect_engines()
        self.services = services

    def choose(self, file_path: str, preference: str = "auto") -> BackendChoice:
        if is_canva_url(file_path):
            return BackendChoice("canva", normalize_canva_url(file_path))
        path = Path(file_path).resolve()
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return BackendChoice("pdf", str(path))
        if suffix in IMAGES:
            return BackendChoice("image", str(path))
        if suffix in VIDEOS:
            return BackendChoice("video", str(path))
        if suffix not in (".ppt", ".pptx"):
            raise BackendUnavailable(
                tr(
                    "Поддерживаются PDF, PowerPoint, изображения и видео. Выберите подходящий тип файла."
                )
            )
        if preference not in self.PREFERENCES:
            raise BackendUnavailable(tr("Неизвестный предпочтительный движок."))
        available = self.availability
        if preference in ("auto", "powerpoint") and available.powerpoint:
            return BackendChoice("powerpoint", str(path))
        if (
            preference == "libreoffice"
            and available.libreoffice
            and available.libreoffice_automation
        ):
            return BackendChoice(
                "libreoffice",
                str(path),
                tr(
                    "Режим LibreOffice: совместимость анимаций, переходов и медиа не гарантируется."
                ),
            )
        if preference in ("auto", "libreoffice", "libreoffice_pdf") and available.libreoffice:
            # Native Impress needs a compatible presenter-console configuration.
            # Automatic fallback is the verified conversion path; native playback
            # remains available as an explicit selection with its own warnings.
            return BackendChoice("libreoffice_pdf", str(path), tr(COMPATIBILITY_WARNING))
        if preference in ("auto", "pdf_copy") and path.with_suffix(".pdf").is_file():
            return BackendChoice("pdf_copy", str(path), tr(COMPATIBILITY_WARNING))
        if preference != "auto":
            raise BackendUnavailable(
                tr(
                    "Выбранный движок недоступен. Выберите «Автоматически», установите нужную программу или подготовьте PDF-копию с тем же именем рядом с презентацией."
                )
            )
        raise BackendUnavailable(
            tr(
                "Microsoft PowerPoint и совместимый LibreOffice не найдены. Установите LibreOffice (libreoffice.org) либо сохраните PDF-копию с тем же именем рядом с презентацией."
            )
        )

    def create(self, choice: BackendChoice, parent=None):
        if choice.kind == "canva":
            from ..backends.canva_backend import CanvaBackend

            return CanvaBackend(parent)
        if choice.kind == "video":
            from ..backends.video_backend import VideoBackend

            return VideoBackend(parent)
        if choice.kind == "image":
            from ..backends.image_backend import ImageBackend

            return ImageBackend(parent)
        if choice.kind == "pdf":
            from ..backends.pdf_backend import PDFBackend

            return PDFBackend(parent)
        if choice.kind in ("pdf_copy", "libreoffice_pdf"):
            from ..backends.converted_pdf_backend import ConvertedPDFBackend

            return ConvertedPDFBackend(choice.kind, self.availability.libreoffice, parent)
        if choice.kind in ("powerpoint", "libreoffice"):
            if self.services is None:
                from ..services.com_worker import OfficeServicePool

                self.services = OfficeServicePool()
            if choice.kind == "powerpoint":
                from ..backends.powerpoint_com_backend import PowerPointCOMBackend

                return PowerPointCOMBackend(self.services.get("powerpoint"), parent)
            from ..backends.libreoffice_backend import LibreOfficeFallbackBackend

            return LibreOfficeFallbackBackend(self.services.get("libreoffice"), parent)
        raise BackendUnavailable(tr("Неизвестный движок презентации."))

    def close(self) -> None:
        if self.services is not None:
            self.services.close()
