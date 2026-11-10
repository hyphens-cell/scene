"""PowerPoint COM objects are created, used and disposed only in the STA worker."""

from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path

from pdf_presenter.i18n import tr

from ..core.capability_model import PresentationDocument
from ..core.media_inspector import inspect_media
from ..core.presentation_file import validate_presentation_file
from ..core.render_service import Raster
from .native_window import (
    find_created_show,
    position_window,
    running_office_pids,
    visible_powerpoint_windows,
    window_handle,
)

log = logging.getLogger(__name__)


class PowerPointSession:
    def __init__(self) -> None:
        self.app = None
        self.owned_application = False
        self.documents = {}
        self.shows = {}
        self.handles = {}
        self.paths = {}
        self.positions = {}
        self.metadata = {}
        self.cache_directory = tempfile.TemporaryDirectory(prefix="pdfpresenter-ppt-")

    def _application(self):
        if self.app is None:
            import win32com.client

            # PowerPoint can reuse a running process even for DispatchEx. Never
            # assume DispatchEx gives exclusive ownership of the application.
            prior_pids = running_office_pids("POWERPNT.EXE")
            try:
                existing = win32com.client.GetActiveObject("PowerPoint.Application")
                del existing
                running = True
            except Exception:
                running = False
            self.app = win32com.client.DispatchEx("PowerPoint.Application")
            self.owned_application = (
                not running and not prior_pids and self.app.Presentations.Count == 0
            )
        return self.app

    def execute(self, document_id: str, method: str, arguments: dict):
        operations = {
            "load": self.load,
            "preview": self.preview,
            "start": self.start,
            "stop": self.stop,
            "next": self.next,
            "previous": self.previous,
            "goto": self.go_to,
            "status": self.status,
            "blank": self.blank,
            "place": self.place,
            "dispose": self.dispose,
            "media_status": self.media_status,
            "play_video": self.play_video,
            "video_control": self.video_control,
            "video_state": self.video_state,
        }
        if method not in operations:
            raise ValueError("Unsupported Office command")
        return operations[method](document_id, **arguments)

    def load(self, document_id: str, path: str):
        source = Path(path).resolve()
        if not source.is_file():
            raise RuntimeError(tr("Файл презентации не найден."))
        validate_presentation_file(source)
        with source.open("rb") as stream:
            fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
        # Queue entries may intentionally repeat a file. Share only documents
        # opened by this session, never adopt an independently opened document.
        for owned_id, owned_path in self.paths.items():
            if owned_path.casefold() == str(source).casefold():
                self.documents[document_id] = self.documents[owned_id]
                self.paths[document_id] = str(source)
                self.positions[document_id] = 0
                self.metadata[document_id] = self.metadata[owned_id]
                return self.metadata[document_id]
        app = self._application()
        # Do not return or later close a presentation independently opened by the user.
        for i in range(1, app.Presentations.Count + 1):
            opened = app.Presentations.Item(i)
            if str(opened.FullName).casefold() == str(source).casefold():
                raise RuntimeError(
                    tr(
                        "Эта презентация уже открыта в PowerPoint. Закройте её там перед загрузкой в Сцена."
                    )
                )
        security, alerts = app.AutomationSecurity, app.DisplayAlerts
        presentation = None
        try:
            app.AutomationSecurity = (
                3  # msoAutomationSecurityForceDisable: never execute document macros.
            )
            app.DisplayAlerts = 1  # ppAlertsNone; scoped to opening our own read-only document.
            presentation = app.Presentations.Open(str(source), -1, 0, 0)
        finally:
            app.AutomationSecurity, app.DisplayAlerts = security, alerts
        try:
            count = int(presentation.Slides.Count)
            if count <= 0:
                raise RuntimeError(tr("Презентация не содержит слайдов."))
            notes = []
            warnings = list(inspect_media(str(source)).warnings)
            for index in range(1, count + 1):
                texts = []
                try:
                    shapes = presentation.Slides.Item(index).NotesPage.Shapes
                    for n in range(1, shapes.Count + 1):
                        shape = shapes.Item(n)
                        # Only speaker body placeholders, not slide number/date/header.
                        if (
                            shape.Type == 14
                            and shape.PlaceholderFormat.Type == 2
                            and shape.HasTextFrame
                        ):
                            if shape.TextFrame.HasText:
                                texts.append(str(shape.TextFrame.TextRange.Text))
                except Exception:
                    if not any(tr("заметки") in value for value in warnings):
                        warnings.append(
                            tr(
                                "Не все заметки PowerPoint удалось прочитать; доступны локальные заметки."
                            )
                        )
                notes.append("\n".join(texts))
            size = (
                float(presentation.PageSetup.SlideWidth),
                float(presentation.PageSetup.SlideHeight),
            )
            self.documents[document_id] = presentation
            self.paths[document_id] = str(source)
            self.positions[document_id] = 0
            result = PresentationDocument(
                str(source),
                fingerprint,
                count,
                source.stem,
                (size,) * count,
                tuple(notes),
                tuple(warnings),
            )
            self.metadata[document_id] = result
            return result
        except Exception:
            if presentation is not None:
                presentation.Saved = -1
                presentation.Close()
            raise

    def preview(self, document_id: str, index: int, width: int, height: int):
        import pymupdf

        presentation = self.documents[document_id]
        slide = presentation.Slides.Item(index + 1)
        ratio = float(presentation.PageSetup.SlideWidth) / max(
            1, float(presentation.PageSetup.SlideHeight)
        )
        width, height = min(4096, width), min(4096, height)
        if width / height > ratio:
            width = max(16, round(height * ratio))
        else:
            height = max(16, round(width / ratio))
        target = Path(self.cache_directory.name) / f"{document_id}-{index}.png"
        slide.Export(str(target), "PNG", width, height)
        pixmap = pymupdf.Pixmap(str(target))
        if pixmap.alpha:
            pixmap = pymupdf.Pixmap(pixmap, 0)
        if pixmap.colorspace.n != 3:
            pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
        result = Raster(pixmap.width, pixmap.height, pixmap.stride, pixmap.samples)
        target.unlink(missing_ok=True)
        return result

    def start(self, document_id: str, index: int, target):
        presentation = self.documents[document_id]
        if document_id in self.shows:
            self.go_to(document_id, index)
            self.place(document_id, target)
            return self.status(document_id)
        settings = presentation.SlideShowSettings
        settings.ShowPresenterView = 0
        settings.ShowType = 2 if target.preview else 1
        settings.ShowScrollbar = 0
        settings.ShowWithAnimation = -1
        settings.ShowWithNarration = -1
        settings.LoopUntilStopped = 0
        # GotoSlide is relative to the configured show range, not the source
        # presentation. Always expose the whole deck so Home/arbitrary jumps work.
        settings.RangeType = 1
        settings.StartingSlide = 1
        settings.EndingSlide = presentation.Slides.Count
        previous_windows = visible_powerpoint_windows()
        show = settings.Run()
        self.shows[document_id] = show
        try:
            # Run already enters slide 1. Re-entering it immediately restarts
            # auto-play media while PowerPoint is still initializing its player.
            if index != 0:
                show.View.GotoSlide(index + 1)
            try:
                hwnd = window_handle(show)
            except Exception:
                hwnd = find_created_show(previous_windows, Path(self.paths[document_id]).stem)
            self.handles[document_id] = hwnd
            position_window(hwnd, target)
            self.positions[document_id] = index
            return self.status(document_id)
        except Exception:
            self.stop(document_id)
            raise

    def _ensure_document(self, document_id: str) -> None:
        if document_id not in self.paths:
            return
        try:
            _ = self.documents[document_id].Slides.Count
            return
        except Exception:
            pass
        # Hidden presentations close with their slideshow on some Office builds.
        # Reopen read-only so previews and repeated F5 remain available.
        app = self._application()
        security, alerts = app.AutomationSecurity, app.DisplayAlerts
        try:
            app.AutomationSecurity, app.DisplayAlerts = 3, 1
            reopened = app.Presentations.Open(self.paths[document_id], -1, 0, 0)
            for other_id, path in self.paths.items():
                if path == self.paths[document_id]:
                    self.documents[other_id] = reopened
        finally:
            app.AutomationSecurity, app.DisplayAlerts = security, alerts

    def stop(self, document_id: str, reopen: bool = True):
        show = self.shows.get(document_id)
        if show is not None:
            try:
                show.View.Exit()
            except Exception:
                import win32gui

                if win32gui.IsWindow(self.handles.get(document_id, 0)):
                    raise
                log.info("Native show already closed", exc_info=True)
        self.shows.pop(document_id, None)
        self.handles.pop(document_id, None)
        if reopen:
            self._ensure_document(document_id)
        return {"active": False, "index": self.positions.get(document_id, 0), "hwnd": 0}

    def next(self, document_id: str):
        if document_id in self.shows:
            self.shows[document_id].View.Next()
        else:
            self.positions[document_id] = min(
                self.documents[document_id].Slides.Count - 1, self.positions[document_id] + 1
            )
        return self.status(document_id)

    def previous(self, document_id: str):
        if document_id in self.shows:
            self.shows[document_id].View.Previous()
        else:
            self.positions[document_id] = max(0, self.positions[document_id] - 1)
        return self.status(document_id)

    def go_to(self, document_id: str, index: int):
        if not 0 <= index < self.documents[document_id].Slides.Count:
            raise ValueError(tr("Номер слайда вне диапазона."))
        if document_id in self.shows:
            self.shows[document_id].View.GotoSlide(index + 1)
        self.positions[document_id] = index
        return self.status(document_id)

    def status(self, document_id: str):
        show = self.shows.get(document_id)
        if show is None:
            return {"active": False, "index": self.positions.get(document_id, 0), "hwnd": 0}
        try:
            state = int(show.View.State)
            if state == 5:
                return {
                    "active": True,
                    "ended": True,
                    "index": self.positions[document_id],
                    "hwnd": self.handles.get(document_id, 0),
                }
            index = int(show.View.Slide.SlideIndex) - 1
            self.positions[document_id] = index
            return {
                "active": True,
                "index": index,
                "hwnd": self.handles.get(document_id, 0),
                "click_index": int(show.View.GetClickIndex()),
                "native_state": state,
            }
        except Exception:
            import win32gui

            if win32gui.IsWindow(self.handles.get(document_id, 0)):
                raise
            self.shows.pop(document_id, None)
            self.handles.pop(document_id, None)
            self._ensure_document(document_id)
            return {
                "active": False,
                "ended": True,
                "index": self.positions.get(document_id, 0),
                "hwnd": 0,
            }

    def blank(self, document_id: str, color: str):
        if document_id in self.shows:
            self.shows[document_id].View.State = {"": 1, "black": 3, "white": 4, "pause": 2}[color]
        return self.status(document_id)

    def play_video(self, document_id: str, index: int, shape_id: int = 0):
        show = self.shows.get(document_id)
        if show is None:
            raise RuntimeError(tr("Сначала начните показ презентации."))
        view = show.View
        if int(view.State) != 1:
            raise RuntimeError(tr("Вернитесь к показу текущего слайда перед запуском видео."))
        slide = view.Slide
        if int(slide.SlideIndex) - 1 != index:
            raise RuntimeError(tr("Слайд изменился. Нажмите «Запустить видео» на нужном слайде."))
        videos = []
        for number in range(1, slide.Shapes.Count + 1):
            shape = slide.Shapes.Item(number)
            if int(shape.Type) == 16 and int(shape.MediaType) == 3:  # msoMedia / movie
                videos.append({"id": int(shape.Id), "name": str(shape.Name)})
        if not videos:
            raise RuntimeError(tr("На текущем слайде нет видео."))
        if not shape_id and len(videos) > 1:
            return {**self.status(document_id), "video_choices": videos}
        selected = next((video for video in videos if video["id"] == shape_id), None)
        if shape_id and selected is None:
            raise RuntimeError(tr("Выбранное видео больше недоступно на текущем слайде."))
        video = selected or videos[0]
        try:
            view.Player(video["id"]).Play()
        except Exception as exc:
            raise RuntimeError(
                tr(
                    "PowerPoint не смог запустить видео. Дождитесь окончания перехода и повторите попытку; проверьте доступность видеофайла."
                )
            ) from exc
        return self.status(document_id)

    def media_status(self, document_id: str):
        """On-demand diagnostics; playback remains entirely inside PowerPoint."""
        show = self.shows.get(document_id)
        if show is None:
            return []
        result = []
        shapes = show.View.Slide.Shapes
        for index in range(1, shapes.Count + 1):
            shape = shapes.Item(index)
            if shape.Type == 16:  # msoMedia
                player = show.View.Player(shape.Id)
                try:
                    state, position = int(player.State), int(player.CurrentPosition)
                except Exception as exc:
                    # E_FAIL while PowerPoint is still creating a native player.
                    if getattr(exc, "excepinfo", None) and exc.excepinfo[-1] == -2147467259:
                        state, position = 3, 0  # ppNotReady
                    else:
                        raise
                result.append({"id": int(shape.Id), "state": state, "position": position})
        return result

    def video_state(self, document_id: str):
        show = self.shows.get(document_id)
        if show is None:
            return {"index": self.positions.get(document_id, 0), "videos": []}
        view, videos = show.View, []
        slide = view.Slide
        for number in range(1, slide.Shapes.Count + 1):
            shape = slide.Shapes.Item(number)
            if int(shape.Type) != 16 or int(shape.MediaType) != 3:
                continue
            state, position, duration = 3, 0, 0
            try:
                duration = max(0, int(shape.MediaFormat.Length))
                player = view.Player(shape.Id)
                state, position = int(player.State), max(0, int(player.CurrentPosition))
            except Exception:
                pass  # A not-yet-created/unsupported native player remains visible as not ready.
            try:
                looping = bool(shape.AnimationSettings.PlaySettings.LoopUntilStopped == -1)
            except Exception:
                looping = None
            videos.append(
                {
                    "id": int(shape.Id),
                    "name": str(shape.Name),
                    "state": state,
                    "position": position,
                    "duration": duration,
                    "volume": None,
                    "loop": looping,
                    "seekable": state != 3 and duration > 0,
                }
            )
        return {"index": int(slide.SlideIndex) - 1, "videos": videos}

    def video_control(self, document_id: str, index: int, shape_id: int, action: str, value=0):
        if action not in {"pause", "stop", "seek", "loop"}:
            raise ValueError(tr("Команда управления видео не поддерживается."))
        show = self.shows.get(document_id)
        if show is None or int(show.View.State) != 1:
            raise RuntimeError(tr("Вернитесь к показу текущего слайда для управления видео."))
        view = show.View
        slide = view.Slide
        if int(slide.SlideIndex) - 1 != index:
            raise RuntimeError(tr("Слайд изменился. Выберите видео на текущем слайде."))
        shape = next(
            (
                slide.Shapes.Item(n)
                for n in range(1, slide.Shapes.Count + 1)
                if int(slide.Shapes.Item(n).Id) == shape_id
            ),
            None,
        )
        if shape is None or int(shape.Type) != 16 or int(shape.MediaType) != 3:
            raise RuntimeError(tr("Выбранное видео недоступно на текущем слайде."))
        if action == "loop":
            shape.AnimationSettings.PlaySettings.LoopUntilStopped = -1 if value else 0
            return self.status(document_id)
        player = view.Player(shape_id)
        try:
            if action == "pause":
                player.Pause()
            elif action == "stop":
                player.Stop()
            else:
                duration = max(0, int(shape.MediaFormat.Length))
                if duration <= 0:
                    raise RuntimeError(tr("Длительность ролика недоступна."))
                player.CurrentPosition = max(0, min(int(value), duration))
        except Exception as exc:
            raise RuntimeError(
                tr("PowerPoint не выполнил команду видео. Дождитесь готовности ролика.")
            ) from exc
        return self.status(document_id)

    def place(self, document_id: str, target):
        if document_id in self.shows:
            position_window(self.handles[document_id], target)
        return self.status(document_id)

    def dispose(self, document_id: str):
        path = self.paths.get(document_id)
        shared = any(
            other_id != document_id and other_path == path
            for other_id, other_path in self.paths.items()
        )
        self.stop(document_id, reopen=shared)
        presentation = self.documents.get(document_id)
        if presentation is not None and not shared:
            try:
                _ = presentation.Slides.Count
            except Exception:
                presentation = None  # Hidden document already closed with its show.
            if presentation is not None:
                presentation.Saved = -1
                presentation.Close()
        self.documents.pop(document_id, None)
        self.paths.pop(document_id, None)
        self.positions.pop(document_id, None)
        self.metadata.pop(document_id, None)
        return True

    def close(self) -> None:
        from .com_worker import _execute_with_retry

        for document_id in list(self.documents):
            try:
                _execute_with_retry(self, document_id, "dispose", {})
            except Exception:
                log.exception("Could not close owned PowerPoint document")
        try:
            if self.app is not None:
                # Do not quit if the user opened any other document while we were running.
                if self.owned_application and self.app.Presentations.Count == 0:
                    self.app.Quit()
        finally:
            self.app = None
            self.cache_directory.cleanup()
