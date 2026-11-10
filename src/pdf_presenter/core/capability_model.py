"""Serializable backend contracts. Slide indices are always zero based."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BackendCapabilities:
    video: bool = False
    video_controls: bool = False
    scaling: bool = False
    audio: bool = False
    animations: bool = False
    transitions: bool = False
    notes: bool = True
    arbitrary_jump: bool = True
    preview: bool = True
    screen_selection: bool = True
    native_window: bool = False
    animation_steps: bool = False
    compatibility: bool = False


@dataclass(frozen=True)
class PresentationDocument:
    path: str
    fingerprint: str
    page_count: int
    title: str
    page_sizes: tuple[tuple[float, float], ...]
    native_notes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DisplayTarget:
    """Qt coordinates plus the Windows device name for native DPI-safe lookup."""

    name: str
    x: int
    y: int
    width: int
    height: int
    preview: bool = False
    cover_hwnd: int = 0
    native_device: str = ""


COMPATIBILITY_WARNING = (
    "Презентация открыта в режиме совместимости. "
    "Анимации, переходы и встроенное видео могут быть недоступны"
)


class BackendError(RuntimeError):
    pass


class BackendUnavailable(BackendError):
    pass
