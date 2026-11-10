from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from pdf_presenter.i18n import tr

from ..core.capability_model import BackendCapabilities, DisplayTarget, PresentationDocument


class PresentationBackend(QObject):
    """Asynchronous abstract interface. Only plain values cross worker boundaries.

    load/prepare complete through loaded, never by blocking the GUI thread.
    ready delivers a bounded RGB raster. started means the audience surface is ready.
    position_changed reports actual state (a native Next may only run an animation).
    """

    loaded = Signal(object)
    load_failed = Signal(str, str)
    ready = Signal(str, int, object)
    failed = Signal(str)
    position_changed = Signal(int)
    started = Signal()
    ended = Signal()
    stopped = Signal()
    native_window_changed = Signal(int)
    video_choices = Signal(int, object)
    video_failed = Signal(str)
    video_state_changed = Signal(int, object)
    frame_ready = Signal(object)

    kind = "abstract"
    label = ""

    def __init__(self, parent: QObject | None = None) -> None:
        if type(self) is PresentationBackend:
            raise TypeError("PresentationBackend is an abstract interface")
        super().__init__(parent)
        self.label = tr(self.label)
        self.document: PresentationDocument | None = None
        self.current = 0
        self.active = False
        self.target: DisplayTarget | None = None
        self.disposed = False
        self.media_settings = {}

    def load(self, file_path: str, password: str = "") -> None:
        raise NotImplementedError

    def prepare(self) -> None:
        if self.document:
            self.get_preview(self.current)

    def start(self, slide_index: int) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def next(self) -> bool:
        raise NotImplementedError

    def previous(self) -> bool:
        raise NotImplementedError

    def go_to_slide(self, index: int) -> bool:
        raise NotImplementedError

    def get_slide_count(self) -> int:
        return self.document.page_count if self.document else 0

    def get_current_slide(self) -> int:
        return self.current

    def get_preview(self, index: int) -> None:
        if self.get_capabilities().preview:
            self.request("preview", index, 960, 600, priority=2)

    def get_capabilities(self) -> BackendCapabilities:
        raise NotImplementedError

    def set_display_target(self, target: DisplayTarget) -> None:
        if not self.get_capabilities().screen_selection:
            raise RuntimeError(tr("Движок не поддерживает выбор экрана."))
        self.target = target

    def set_media_settings(self, settings: dict) -> None:
        self.media_settings = dict(settings)

    def begin_frame(self) -> None:
        raise NotImplementedError

    def request(self, tag: str, page: int, width: int, height: int, priority: int = 0) -> None:
        raise NotImplementedError

    def set_blank(self, color: str) -> None:
        """PDF blanking is owned by AudienceDisplayManager; native engines override."""

    def play_video(self, shape_id: int = 0, *, slide_index: int | None = None) -> bool:
        """Start a native video only when the backend supports playback controls."""
        return False

    def control_video(self, action: str, shape_id: int, *, slide_index: int, value=0) -> bool:
        return False

    def dispose(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        self.dispose()
