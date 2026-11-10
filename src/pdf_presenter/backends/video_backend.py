"""Local Qt/FFmpeg playback; its own audience window shares the handoff contract."""

from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtMultimedia import QAudioOutput, QMediaMetaData, QMediaPlayer, QtVideo, QVideoFrame
from PySide6.QtWidgets import QApplication

from pdf_presenter.i18n import tr

from ..core.capability_model import BackendCapabilities, PresentationDocument
from ..core.render_service import Raster, RasterCache
from ..ui.video_surface import VideoSurface
from .base_backend import PresentationBackend


class VideoBackend(PresentationBackend):
    kind = "video"
    label = "Видеофайл"
    frame_ready = Signal(object)
    _fingerprint_ready = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.surface = VideoSurface()
        self.surface.closed.connect(self._surface_closed)
        self.player.setVideoOutput(self.surface.video)
        self.surface.video.videoSink().videoFrameChanged.connect(
            self._frame, Qt.ConnectionType.QueuedConnection
        )
        self.player.mediaStatusChanged.connect(
            self._media_status, Qt.ConnectionType.QueuedConnection
        )
        self.player.errorOccurred.connect(self._error)
        self.player.positionChanged.connect(self._emit_state)
        self.player.playbackStateChanged.connect(self._emit_state)
        self.audio.volumeChanged.connect(self._emit_state)
        self._fingerprint_ready.connect(self._fingerprint, Qt.ConnectionType.QueuedConnection)
        self.path = ""
        self.fingerprint = ""
        self._loaded_media = False
        self._cancel_hash = threading.Event()
        self._starting = False
        self._covered_playing = False
        self.native_hwnd = 0
        self._last_preview = 0.0
        self._preview = QImage()
        self.cache = RasterCache(16 * 1024 * 1024)
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.setInterval(30000)
        self._load_timer.timeout.connect(
            lambda: self._error(None, tr("Загрузка видео превысила 30 секунд."))
        )

    @property
    def pending_count(self):
        return int(self._load_timer.isActive())

    def get_capabilities(self):
        return BackendCapabilities(
            video=True, video_controls=True, audio=True, scaling=True, native_window=True
        )

    def load(self, file_path: str, password=""):
        source = Path(file_path).resolve()
        if not source.is_file():
            self.load_failed.emit("document", tr("Видеофайл не найден."))
            return
        self.path = str(source)
        cancel = self._cancel_hash

        def fingerprint():
            try:
                digest = hashlib.sha256()
                with source.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        if cancel.is_set():
                            return
                        digest.update(chunk)
                if not cancel.is_set():
                    self._fingerprint_ready.emit(digest.hexdigest(), "")
            except (OSError, RuntimeError) as exc:
                if not cancel.is_set():
                    self._fingerprint_ready.emit("", str(exc))

        QThreadPool.globalInstance().start(fingerprint)
        self._load_timer.start()
        self.player.setSource(QUrl.fromLocalFile(self.path))

    @Slot(str, str)
    def _fingerprint(self, value, error):
        if self.disposed:
            return
        if error:
            self._error(None, error)
            return
        self.fingerprint = value
        self._finish_load()

    @Slot(QMediaPlayer.MediaStatus)
    def _media_status(self, status):
        if self.disposed:
            return
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self._loaded_media = True
            self._finish_load()
        elif (
            status == QMediaPlayer.MediaStatus.EndOfMedia
            and self.active
            and self.player.mediaStatus() == status
            and not self.media_settings.get("loop", False)
        ):
            self._emit_state()
            self.ended.emit()

    def _finish_load(self):
        if not self._loaded_media or not self.fingerprint or self.document is not None:
            return
        if not self.player.hasVideo():
            self._error(None, tr("Файл не содержит поддерживаемой видеодорожки."))
            return
        resolution = self.player.metaData().value(QMediaMetaData.Key.Resolution)
        width = resolution.width() if resolution and resolution.width() > 0 else 1280
        height = resolution.height() if resolution and resolution.height() > 0 else 720
        orientation = self.player.metaData().value(QMediaMetaData.Key.Orientation)
        angle = (
            orientation.value
            if isinstance(orientation, QtVideo.Rotation)
            else int(orientation or 0)
        )
        if angle % 180 == 90:
            width, height = height, width
        self.document = PresentationDocument(
            self.path, self.fingerprint, 1, Path(self.path).name, ((float(width), float(height)),)
        )
        self.set_media_settings(self.media_settings)
        self._load_timer.stop()
        self._preview = QImage(960, 540, QImage.Format.Format_RGB888)
        self._preview.fill(QColor("#111827"))
        painter = QPainter(self._preview)
        painter.setPen(QColor("#D9E6FF"))
        font = painter.font()
        font.setPixelSize(28)
        painter.setFont(font)
        painter.drawText(
            self._preview.rect().adjusted(60, 60, -60, -60),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            tr("ВИДЕО\n{p0}\n\nНачните показ для воспроизведения", p0=Path(self.path).name),
        )
        painter.end()
        self.loaded.emit(self.document)

    @Slot(QMediaPlayer.Error, str)
    def _error(self, _, message):
        if self.disposed:
            return
        self._load_timer.stop()
        text = tr(
            "Не удалось воспроизвести видео: {p0}. Проверьте файл и поддержку его кодека.",
            p0=message,
        )
        if self.document is None:
            self.load_failed.emit("document", text)
        else:
            self.active = self._starting = False
            self.failed.emit(text)

    def start(self, slide_index: int):
        if self.document is None or self.target is None or self.disposed or slide_index != 0:
            return
        self._starting = True
        self._place()
        if self.player.position() != 0:
            self.player.setPosition(0)
        self.player.play()

    def _place(self):
        if self.target is None:
            return
        if QApplication.platformName() == "offscreen":
            self.surface.resize(640, 360)
            self.surface.show()
        else:
            screen = next(
                (screen for screen in QApplication.screens() if screen.name() == self.target.name),
                None,
            )
            if screen is None:
                raise RuntimeError(tr("Выбранный экран отключён. Показ видео остановлен."))
            # This window belongs to Qt. Keep Qt's fullscreen state in sync;
            # stripping styles through Win32 is undone when a native video child appears.
            self.surface.hide()
            self.surface.setWindowFlag(Qt.WindowType.FramelessWindowHint, not self.target.preview)
            self.surface.winId()
            self.surface.windowHandle().setScreen(screen)
            area = screen.availableGeometry() if self.target.preview else screen.geometry()
            if self.target.preview:
                width, height = min(800, area.width() * 2 // 3), min(500, area.height() * 2 // 3)
                self.surface.setGeometry(
                    area.right() - width - 24, area.bottom() - height - 24, width, height
                )
                self.surface.showNormal()
            else:
                self.surface.setGeometry(area)
                self.surface.windowHandle().setGeometry(area)
                self.surface.showFullScreen()
        self.native_hwnd = int(self.surface.winId())
        self.native_window_changed.emit(self.native_hwnd)

    def set_display_target(self, target):
        super().set_display_target(target)
        if self.active:
            self._place()

    def set_media_settings(self, settings):
        super().set_media_settings(settings)
        self.audio.setVolume(self.media_settings.get("volume", 100) / 100)
        self.player.setLoops(
            QMediaPlayer.Loops.Infinite
            if self.media_settings.get("loop", False)
            else QMediaPlayer.Loops.Once
        )
        if self.document:
            self.surface.set_media_view(self.document.page_sizes[0], self.media_settings)

    def _surface_closed(self):
        if self.active or self._starting:
            self.stop()
            self.failed.emit(tr("Окно видео закрыто. Запустите показ повторно."))

    @Slot(QVideoFrame)
    def _frame(self, frame):
        if not frame.isValid() or self.disposed:
            return
        if self._starting:
            self._starting = False
            self.active = True
            self.started.emit()
            self._emit_state()
        now = time.monotonic()
        if self.active and (
            now - self._last_preview >= 0.15
            or self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
        ):
            self._last_preview = now
            image = frame.toImage()
            if not image.isNull():
                self._preview = image.scaled(
                    960,
                    600,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.frame_ready.emit(self._preview)

    @Slot()
    def _emit_state(self, *_):
        if self.disposed or self.document is None:
            return
        state = {
            QMediaPlayer.PlaybackState.PlayingState: 0,
            QMediaPlayer.PlaybackState.PausedState: 1,
            QMediaPlayer.PlaybackState.StoppedState: 2,
        }[self.player.playbackState()]
        self.video_state_changed.emit(
            0,
            [
                {
                    "id": 1,
                    "name": Path(self.path).name,
                    "state": state,
                    "position": self.player.position(),
                    "duration": self.player.duration(),
                    "volume": round(self.audio.volume() * 100),
                    "seekable": self.player.isSeekable(),
                    "loop": bool(self.media_settings.get("loop", False)),
                }
            ],
        )

    def control_video(self, action, shape_id, *, slide_index, value=0):
        if not self.active or self.disposed or slide_index != 0 or shape_id != 1:
            return False
        if action == "play":
            self.player.play()
        elif action == "pause":
            self.player.pause()
        elif action == "stop":
            self.player.stop()
        elif action == "seek" and self.player.isSeekable():
            self.player.setPosition(max(0, min(int(value), self.player.duration())))
        elif action == "volume":
            self.media_settings["volume"] = max(0, min(int(value), 100))
            self.audio.setVolume(self.media_settings["volume"] / 100)
        elif action == "loop":
            self.media_settings["loop"] = bool(value)
            self.player.setLoops(QMediaPlayer.Loops.Infinite if value else QMediaPlayer.Loops.Once)
        else:
            return False
        self._emit_state()
        return True

    def play_video(self, shape_id=0, *, slide_index=None):
        return self.control_video("play", shape_id or 1, slide_index=slide_index or 0)

    def set_blank(self, color):
        if self.disposed or not (self.active or self._starting):
            return
        if color:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._covered_playing = True
                self.player.pause()
        elif self._covered_playing:
            self._covered_playing = False
            self.player.play()

    def stop(self):
        self.active = self._starting = self._covered_playing = False
        self.player.stop()
        self.surface.hide()
        self.native_hwnd = 0
        self.native_window_changed.emit(0)
        self.stopped.emit()

    def next(self):
        if self.active:
            self.ended.emit()
        return False

    def previous(self):
        return self.go_to_slide(0)

    def go_to_slide(self, index):
        if index != 0 or self.document is None:
            return False
        self.current = 0
        self.position_changed.emit(0)
        return True

    def begin_frame(self):
        pass  # QVideoWidget renders the native video; request() only serves its latest preview.

    def request(self, tag, page, width, height, priority=0):
        if page != 0 or self._preview.isNull() or self.disposed:
            return
        image = self._preview.scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        image = image.convertToFormat(QImage.Format.Format_RGB888)
        self.ready.emit(
            tag,
            0,
            Raster(image.width(), image.height(), image.bytesPerLine(), bytes(image.constBits())),
        )

    def dispose(self):
        if not self.disposed:
            self._cancel_hash.set()
            self._load_timer.stop()
            self.stop()
            self.disposed = True
            self.player.setSource(QUrl())
            self.player.setVideoOutput(None)
            self.surface.close()
            self.surface.deleteLater()
            self.cache.clear()
