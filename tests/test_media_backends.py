import hashlib
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtMultimedia import QMediaPlayer

from pdf_presenter.backends.image_backend import ImageBackend
from pdf_presenter.backends.video_backend import VideoBackend
from pdf_presenter.core.backend_manager import BackendManager, EngineAvailability


@pytest.mark.parametrize("extension", ["png", "jpg", "bmp", "webp", "tiff"])
def test_standalone_image_decode_preview_and_source_preservation(qtbot, tmp_path, extension):
    image = QImage(320, 180, QImage.Format.Format_ARGB32)
    image.fill(QColor("#27a370"))
    path = tmp_path / f"picture.{extension}"
    assert image.save(str(path))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manager = BackendManager(EngineAvailability())
    backend = manager.create(manager.choose(str(path)))
    assert isinstance(backend, ImageBackend)
    errors, rasters = [], []
    backend.load_failed.connect(lambda *args: errors.append(args))
    backend.failed.connect(errors.append)
    backend.ready.connect(lambda *args: rasters.append(args))
    try:
        backend.load(str(path))
        qtbot.waitUntil(lambda: backend.document is not None or bool(errors), timeout=15000)
        assert not errors and backend.document.page_sizes == ((320, 180),)
        backend.request("current", 0, 160, 90)
        qtbot.waitUntil(lambda: bool(rasters) or bool(errors), timeout=10000)
        assert not errors
        raster = rasters[0][2]
        assert (raster.width, raster.height) == (160, 90)
        assert backend.get_capabilities().scaling
    finally:
        backend.dispose()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_video_preparation_is_silent_and_does_not_open_audience(qtbot):
    path = Path("artifacts/v2-media/moving-pattern.mp4").resolve()
    if not path.is_file():
        pytest.skip("Generate the native media fixture first")
    backend = VideoBackend()
    errors, previews = [], []
    backend.load_failed.connect(lambda *args: errors.append(args))
    backend.ready.connect(lambda *args: previews.append(args))
    try:
        backend.load(str(path))
        qtbot.waitUntil(lambda: backend.document is not None or bool(errors), timeout=30000)
        assert not errors and backend.document.page_count == 1
        assert backend.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
        assert not backend.surface.isVisible() and not backend.active
        backend.set_blank("black")
        backend.set_blank("")
        assert backend.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
        backend.get_preview(0)
        assert previews and previews[0][2].samples
    finally:
        backend.dispose()


def test_damaged_video_reports_load_error_without_playback(qtbot, tmp_path):
    path = tmp_path / "broken.mp4"
    path.write_bytes(b"not a video")
    backend = VideoBackend()
    errors = []
    backend.load_failed.connect(lambda *args: errors.append(args))
    try:
        backend.load(str(path))
        qtbot.waitUntil(lambda: bool(errors), timeout=15000)
        assert backend.document is None and not backend.surface.isVisible()
    finally:
        backend.dispose()
