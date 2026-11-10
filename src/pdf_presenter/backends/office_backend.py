from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import QTimer

from pdf_presenter.i18n import tr

from ..core.render_service import RasterCache
from .base_backend import PresentationBackend


class OfficeBackend(PresentationBackend):
    """Qt-side adapter. Contains no COM proxies and never calls Office directly."""

    def __init__(self, service, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.document_id = uuid4().hex
        self.native_hwnd = 0
        self.click_index = 0
        self.native_state = 0
        self.cache = RasterCache(64 * 1024 * 1024)
        self._commands = {}
        self._pending_renders = {}
        self._epoch = 0
        self._poll_pending = False
        self._video_pending = False
        self._video_tick = 0
        self._starting = False
        self._stopping = False
        self._ended_notified = False
        service.completed.connect(self._completed)
        service.failed.connect(self._failed)
        service.disconnected.connect(self._disconnected)
        self._poller = QTimer(self)
        self._poller.setInterval(180)
        self._poller.timeout.connect(self._poll_state)
        self._poller.start()

    @property
    def pending_count(self) -> int:
        return len(self._pending_renders)

    def _call(self, method: str, arguments=None, *, priority=0, timeout=15, context=None):
        request_id = self.service.call(
            self.document_id, method, arguments, priority=priority, timeout=timeout
        )
        self._commands[request_id] = (method, context)
        return request_id

    def load(self, file_path: str, password: str = "") -> None:
        self._call("load", {"path": file_path}, timeout=45)

    def _completed(self, document_id: str, request_id: str, result) -> None:
        if document_id != self.document_id or self.disposed:
            return
        command = self._commands.pop(request_id, None)
        if command is None:
            return
        method, context = command
        if method == "load":
            self.document = result
            self.current = 0
            self.loaded.emit(result)
        elif method == "preview":
            epoch, key = context
            self.cache.put(key, result)
            waiting = self._pending_renders.get(key)
            if waiting and waiting[0] == epoch:
                self._pending_renders.pop(key, None)
            if waiting and epoch == self._epoch:
                for tag in waiting[1]:
                    self.ready.emit(tag, key[0], result)
        elif method == "dispose":
            return
        elif method == "video_state":
            self._video_pending = False
            if self.active and result.get("index") == self.current:
                self.video_state_changed.emit(self.current, result.get("videos", []))
        else:
            if method == "status":
                self._poll_pending = False
            previous_active = self.active
            self.current = result.get("index", self.current)
            self.active = result.get("active", self.active)
            hwnd = result.get("hwnd", self.native_hwnd)
            if self.native_hwnd != hwnd:
                self.native_hwnd = hwnd
                self.native_window_changed.emit(hwnd)
            self.click_index = result.get("click_index", self.click_index)
            self.native_state = result.get("native_state", self.native_state)
            self.position_changed.emit(self.current)
            if method == "start":
                self._starting = False
                self._ended_notified = False
                if self.active:
                    self.started.emit()
                else:
                    self.failed.emit(tr("PowerPoint не создал готовое окно показа."))
            if method == "stop":
                self._stopping = False
                self.stopped.emit()
            elif (
                (result.get("ended") or (previous_active and not self.active))
                and not self._stopping
                and not self._ended_notified
            ):
                self._ended_notified = True
                self.ended.emit()
            if method == "play_video" and result.get("video_choices"):
                self.video_choices.emit(result["index"], result["video_choices"])

    def _failed(self, document_id: str, request_id: str, message: str) -> None:
        if document_id != self.document_id or self.disposed:
            return
        method, context = self._commands.pop(request_id, ("", None))
        if method == "video_state":
            self._video_pending = False
            return  # State polling remains the authoritative connection check.
        if method in {"play_video", "video_control"}:
            # A missing/unavailable clip must not end the presentation. Actual
            # worker loss is handled separately by _disconnected/status polling.
            self.video_failed.emit(message)
            return
        self._poll_pending = False
        self._starting = False
        if method == "load":
            self.load_failed.emit("document", f"{self.label}: {message}")
        elif method == "preview":
            if context:
                self._pending_renders.pop(context[1], None)
            self.failed.emit(tr("Предпросмотр {p0}: {p1}", p0=self.label, p1=message))
        else:
            self.active = False
            self._stopping = False
            self.failed.emit(f"{self.label}: {message}")

    def _disconnected(self, message: str) -> None:
        if self.disposed:
            return
        loading = any(method == "load" for method, _ in self._commands.values())
        self._commands.clear()
        self._pending_renders.clear()
        self.active = False
        self.native_hwnd = 0
        self._poll_pending = self._starting = False
        self._video_pending = False
        self.native_window_changed.emit(0)
        if loading:
            self.load_failed.emit("document", message)
        else:
            self.failed.emit(message)

    def _poll_state(self) -> None:
        if self.active and not self._poll_pending and not self.disposed:
            self._poll_pending = True
            self._call("status", priority=1, timeout=8)
        self._video_tick += 1
        if (
            self.active
            and not self.disposed
            and not self._stopping
            and self.get_capabilities().video_controls
            and not self._video_pending
            and self._video_tick % 3 == 0
        ):
            self._video_pending = True
            self._call("video_state", priority=2, timeout=8)

    def start(self, slide_index: int) -> None:
        if self._starting or not 0 <= slide_index < self.get_slide_count():
            return
        if self.target is None:
            self.failed.emit(tr("Сначала выберите экран аудитории."))
            return
        self._starting = True
        self._call("start", {"index": slide_index, "target": self.target}, priority=-2, timeout=20)

    def stop(self) -> None:
        if self.document is not None and not self.disposed:
            cancelled = self.service.cancel_methods(
                self.document_id,
                {
                    "start",
                    "goto",
                    "next",
                    "previous",
                    "place",
                    "blank",
                    "status",
                    "play_video",
                    "video_control",
                    "video_state",
                },
            )
            for request_id in cancelled:
                self._commands.pop(request_id, None)
            self._poll_pending = self._starting = False
            self._video_pending = False
            self._stopping = True
            self._call("stop", priority=-3, timeout=8)

    def next(self) -> bool:
        if not self.document or self.disposed:
            return False
        self._call("next", priority=-1, timeout=8)
        return True

    def previous(self) -> bool:
        if not self.document or self.disposed:
            return False
        self._call("previous", priority=-1, timeout=8)
        return True

    def go_to_slide(self, index: int) -> bool:
        if (
            not self.get_capabilities().arbitrary_jump
            or not 0 <= index < self.get_slide_count()
            or self.disposed
        ):
            return False
        self._call("goto", {"index": index}, priority=-1, timeout=8)
        return True

    def set_display_target(self, target) -> None:
        super().set_display_target(target)
        if self.active:
            self._call("place", {"target": target}, priority=-2, timeout=8)

    def set_blank(self, color: str) -> None:
        if self.active and not self.disposed:
            self._call("blank", {"color": color}, priority=-2, timeout=8)

    def play_video(self, shape_id: int = 0, *, slide_index: int | None = None) -> bool:
        if (
            not self.get_capabilities().video_controls
            or not self.active
            or self.disposed
            or self._stopping
            or any(method == "play_video" for method, _ in self._commands.values())
        ):
            return False
        self._call(
            "play_video",
            {"index": self.current if slide_index is None else slide_index, "shape_id": shape_id},
            priority=-1,
            timeout=8,
        )
        return True

    def control_video(self, action: str, shape_id: int, *, slide_index: int, value=0) -> bool:
        if action == "play":
            return self.play_video(shape_id, slide_index=slide_index)
        if (
            not self.get_capabilities().video_controls
            or not self.active
            or self.disposed
            or self._stopping
        ):
            return False
        self._call(
            "video_control",
            {"action": action, "shape_id": shape_id, "index": slide_index, "value": value},
            priority=-1,
            timeout=8,
        )
        return True

    def begin_frame(self) -> None:
        self._epoch += 1
        cancelled = self.service.cancel_previews(self.document_id)
        for request_id in cancelled:
            self._commands.pop(request_id, None)
        self._pending_renders.clear()
        # Keep the in-flight metadata: its result may still populate the LRU cache.

    def request(self, tag: str, page: int, width: int, height: int, priority: int = 0) -> None:
        if (
            not self.get_capabilities().preview
            or not 0 <= page < self.get_slide_count()
            or self.disposed
        ):
            return
        key = (page, max(16, min(width, 4096)), max(16, min(height, 4096)))
        raster = self.cache.get(key)
        if raster is not None:
            self.ready.emit(tag, page, raster)
            return
        waiting = self._pending_renders.get(key)
        if waiting:
            if tag not in waiting[1]:
                waiting[1].append(tag)
            return
        self._pending_renders[key] = (self._epoch, [tag])
        self._call(
            "preview",
            {"index": page, "width": key[1], "height": key[2]},
            priority=10 + priority,
            context=(self._epoch, key),
        )

    def dispose(self) -> None:
        if not self.disposed:
            self.service.cancel_document(self.document_id)
            # Also queues after a currently running load so its document gets closed.
            self._call("dispose", priority=-4, timeout=10)
            self.disposed = True
            self.active = False
            self._poller.stop()
            self.cache.clear()
            self._commands.clear()
            self._pending_renders.clear()
            self.service.completed.disconnect(self._completed)
            self.service.failed.disconnect(self._failed)
            self.service.disconnected.disconnect(self._disconnected)
