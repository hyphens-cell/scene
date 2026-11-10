"""Opt-in real two-screen Qt/FFmpeg playback. Does not build or install anything."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtMultimedia import QMediaPlayer

from pdf_presenter.backends.video_backend import VideoBackend
from pdf_presenter.core.capability_model import DisplayTarget
from pdf_presenter.core.project_manager import ProjectManager
from pdf_presenter.services.audience_capture import capture_show, desktop_available
from pdf_presenter.ui.presenter_window import PresenterWindow
from pdf_presenter.ui.styles import apply_theme

pytestmark = pytest.mark.skipif(
    os.environ.get("SCENE_NATIVE_MEDIA_TESTS") != "1", reason="Explicit native media run required"
)


def test_video_loop_overrides_auto_advance_until_disabled(qtbot, qapp, tmp_path, pdf_factory):
    if qapp.platformName() != "windows":
        pytest.skip("Native Windows player required")
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors = []
    window._warning = errors.append
    window.show()
    entries = window.queue.add(
        [Path("artifacts/v2-media/moving-pattern.mp4").resolve(), pdf_factory(2)]
    )
    entries[0].media_settings = {"volume": 0}
    window.project.auto_advance = True
    try:
        window.load_item(entries[0].id)
        qtbot.waitUntil(lambda: window.document is not None and not window.loading, timeout=15000)
        window.start_presentation()
        qtbot.waitUntil(lambda: window.renderer.active and not window.handoff.busy, timeout=10000)
        qtbot.waitUntil(lambda: window.navigation.media.repeat.isEnabled(), timeout=5000)
        backend = window.renderer
        window.navigation.media.repeat.click()
        assert entries[0].media_settings["loop"] is True
        for _ in range(2):
            backend.player.setPosition(backend.player.duration() - 150)
            qtbot.waitUntil(lambda: backend.player.position() < 1500, timeout=5000)
            assert window.queue.active_id == entries[0].id and backend.active
        window.navigation.media.stop.click()
        qtbot.wait(400)
        assert backend.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
        window.navigation.media.play.click()
        qtbot.waitUntil(lambda: backend.player.position() > 100)
        window.navigation.media.repeat.click()
        assert entries[0].media_settings["loop"] is False
        backend.player.setPosition(backend.player.duration() - 150)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[1].id and not window.loading, timeout=12000
        )
        assert not errors and window.presentation.active
    finally:
        window._project_dirty = False
        window.close()


def test_video_player_queue_scale_volume_and_cleanup(
    qtbot, qapp, tmp_path, pdf_factory, monkeypatch
):
    if qapp.platformName() != "windows" or len(qapp.screens()) < 2 or not desktop_available():
        pytest.skip("Requires an unlocked Windows desktop with two screens")
    import win32gui

    source = Path("artifacts/v2-media/moving-pattern.mp4").resolve()
    assert source.is_file()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    image_path = tmp_path / "image.png"
    image = QImage(400, 400, QImage.Format.Format_RGB32)
    image.fill(QColor("#226644"))
    assert image.save(str(image_path))
    apply_theme(qapp)
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.show()
    screen = window.monitors.default_audience(window.screen())
    window.monitor_combo.setCurrentIndex(window.monitor_combo.findData(screen.name()))
    output = Path("artifacts/scene-native")
    output.mkdir(exist_ok=True)
    entries = window.queue.add([image_path, source, pdf_factory(3)])
    entries[1].media_settings = {"volume": 20}
    backend = None
    try:
        window.load_item(entries[0].id)
        qtbot.waitUntil(lambda: window.document is not None and not window.loading, timeout=15000)
        window.start_presentation()
        qtbot.waitUntil(lambda: window.renderer.active and not window.handoff.busy, timeout=10000)
        start_time = window.timer._started
        window.load_item(entries[1].id)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[1].id and not window.handoff.busy,
            timeout=25000,
        )
        backend = window.renderer
        qtbot.waitUntil(
            lambda: backend.player.position() > 800 and window.navigation.media.play.isEnabled(),
            timeout=10000,
        )
        assert backend.active and backend.surface.isVisible()
        assert backend.audio.volume() == pytest.approx(0.2)
        hwnd = backend.native_hwnd
        first = capture_show(hwnd)
        assert not first.isNull()
        qtbot.wait(600)
        second = capture_show(hwnd)
        assert not second.isNull() and first != second
        second.save(str(output / "audience-video.png"))
        qtbot.mouseClick(window.navigation.media.play, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: backend.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
        )
        paused = backend.player.position()
        qtbot.wait(250)
        assert abs(backend.player.position() - paused) < 100
        window.navigation.media.seek.setValue(7000)
        qtbot.waitUntil(lambda: abs(backend.player.position() - 7000) < 150)
        assert backend.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
        window.navigation.media.volume.setValue(37)
        window.navigation.media.seek.setFocus()
        qtbot.keyClick(window.navigation.media.seek, Qt.Key.Key_Left)
        qtbot.waitUntil(lambda: abs(backend.player.position() - 6000) < 150)
        assert window.queue.active_id == entries[1].id
        window.navigation.media.seek.setValue(7000)
        assert backend.audio.volume() == pytest.approx(0.37)
        assert entries[1].media_settings["volume"] == 37
        window.navigation.scale.mode.setCurrentIndex(window.navigation.scale.mode.findData("zoom"))
        window.navigation.scale.zoom.setValue(400)
        assert backend.surface.video.width() > backend.surface.width()
        assert window.current_slide.view_settings["zoom"] == 400
        window.resize(1024, 768)
        qtbot.wait(200)
        window.grab().save(str(output / "presenter-small.png"))
        window.resize(1440, 900)
        qtbot.wait(200)
        window.grab().save(str(output / "presenter.png"))
        viewport, _ = window.current_slide.content_rects()
        preview = (
            window.current_slide.grab().toImage().copy(viewport.toAlignedRect()).scaled(64, 36)
        )
        audience = capture_show(hwnd).scaled(64, 36)
        assert not audience.isNull()
        difference = sum(
            abs(a - b)
            for y in range(36)
            for x in range(64)
            for a, b in zip(
                preview.pixelColor(x, y).getRgb()[:3],
                audience.pixelColor(x, y).getRgb()[:3],
                strict=True,
            )
        ) / (64 * 36 * 3)
        assert difference < 15, "Presenter crop must match the actual audience pixels"
        window.set_audience_mode("hold")
        assert backend.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
        assert window.audience.slide.view_source is None
        window.set_audience_mode("slide")
        assert backend.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
        qtbot.mouseClick(window.navigation.media.play, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: backend.player.position() > 7300)
        window.presentation.toggle_blank("black")
        assert backend.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
        window.presentation.toggle_blank("black")
        qtbot.waitUntil(
            lambda: backend.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        qtbot.mouseClick(window.navigation.media.stop, Qt.MouseButton.LeftButton)
        assert backend.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
        assert window.presentation.active and backend.active and backend.player.position() == 0
        window.presentation.toggle_blank("black")
        window.presentation.toggle_blank("black")
        assert backend.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
        qtbot.mouseClick(window.navigation.media.play, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: backend.player.position() > 400)
        window.load_item(entries[2].id)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[2].id and not window.loading, timeout=15000
        )
        qtbot.waitUntil(lambda: not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd))
        assert (
            backend.disposed and window.presentation.active and window.timer._started == start_time
        )
        assert not window.navigation.media.isVisible() and window.current_slide.view_source is None
        window.project.path = tmp_path / "mixed.pdfpresenter"
        assert window.save_project()
        restored, warning = ProjectManager().load(window.project.path)
        assert not warning and restored.items[1].media_settings["volume"] == 37
        assert restored.items[1].media_settings["zoom"] == 400
        assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
        assert not errors
        (output / "report.json").write_text(
            json.dumps(
                {
                    "success": True,
                    "moving_pixels": True,
                    "pause_seek_resume_stop": True,
                    "volume": 37,
                    "zoom": 400,
                    "queue": "image -> video -> PDF",
                    "timer_preserved": True,
                    "video_window_closed": True,
                    "source_unchanged": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        window._project_dirty = False
        window.close()


@pytest.mark.parametrize(
    "filename",
    [
        "h264.mp4",
        "h265.mp4",
        "mpeg4.m4v",
        "h264.mkv",
        "mpeg4.avi",
        "h264.mov",
        "vp9.webm",
        "wmv.wmv",
        "wmv.asf",
        "mpeg.mpg",
        "mpeg.mpeg",
        "h264.ts",
        "h264.mts",
        "h264.m2ts",
        "dvd.vob",
        "theora.ogv",
        "h264.flv",
        "mobile.3gp",
        "portrait.mp4",
    ],
)
def test_actual_decoder_formats(qtbot, qapp, filename):
    if qapp.platformName() != "windows" or len(qapp.screens()) < 2 or not desktop_available():
        pytest.skip("Requires an unlocked Windows desktop with two screens")
    source = Path("artifacts/scene-formats") / filename
    assert source.is_file(), "Run scripts/make_video_formats.py first"
    screen = qapp.screens()[-1]
    area = screen.geometry()
    backend = VideoBackend()
    backend.set_media_settings({"volume": 0})
    backend.set_display_target(
        DisplayTarget(screen.name(), area.x(), area.y(), area.width(), area.height())
    )
    errors, frames = [], []
    backend.load_failed.connect(lambda *args: errors.append(args))
    backend.failed.connect(errors.append)
    backend.frame_ready.connect(frames.append)
    try:
        backend.load(str(source))
        qtbot.waitUntil(lambda: backend.document is not None or bool(errors), timeout=15000)
        assert not errors and backend.player.hasVideo() and backend.player.hasAudio()
        assert backend.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
        backend.start(0)
        qtbot.waitUntil(
            lambda: (backend.active and len(frames) >= 2) or bool(errors), timeout=10000
        )
        assert not errors and frames[0] != frames[-1], (
            "Must decode changing frames, not just metadata"
        )
        if filename == "portrait.mp4":
            assert backend.document.page_sizes == ((180, 320),)
            assert frames[-1].width() < frames[-1].height()
            assert backend.surface.video.width() / backend.surface.video.height() == pytest.approx(
                180 / 320, abs=0.01
            )
    finally:
        backend.dispose()


def test_video_end_auto_advance_restart_and_window_close(
    qtbot, qapp, tmp_path, pdf_factory, monkeypatch
):
    if qapp.platformName() != "windows" or len(qapp.screens()) < 2 or not desktop_available():
        pytest.skip("Requires an unlocked Windows desktop with two screens")
    source = Path("artifacts/v2-media/moving-pattern.mp4").resolve()
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.show()
    screen = window.monitors.default_audience(window.screen())
    window.monitor_combo.setCurrentIndex(window.monitor_combo.findData(screen.name()))
    entries = window.queue.add([source, pdf_factory(2)])
    entries[0].media_settings = {"volume": 0}
    try:
        window.load_item(entries[0].id)
        qtbot.waitUntil(lambda: window.document is not None and not window.loading, timeout=15000)
        window.start_presentation()
        qtbot.waitUntil(lambda: window.renderer.active and not window.handoff.busy, timeout=10000)
        backend = window.renderer
        backend.player.setPosition(backend.player.duration() - 100)
        qtbot.waitUntil(
            lambda: backend.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia,
            timeout=5000,
        )
        assert window.presentation.active and window.queue.active_id == entries[0].id
        window.start_presentation()
        qtbot.waitUntil(
            lambda: backend.player.position() > 100 and backend.player.position() < 1000,
            timeout=5000,
        )
        window.project.auto_advance = True
        backend.player.setPosition(backend.player.duration() - 100)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[1].id and not window.loading, timeout=10000
        )
        assert window.presentation.active
        window.load_item(entries[0].id)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[0].id and not window.handoff.busy,
            timeout=10000,
        )
        window.renderer.surface.close()
        qtbot.waitUntil(lambda: not window.presentation.active, timeout=5000)
        assert window.audience.slide.blank == "black" and not window.renderer.active
        assert not errors
    finally:
        window._project_dirty = False
        window.close()


@pytest.mark.skipif(
    os.environ.get("PDFPRESENTER_POWERPOINT_TESTS") != "1",
    reason="Explicit real PowerPoint run required",
)
def test_standalone_video_to_powerpoint_to_image(qtbot, qapp, tmp_path, monkeypatch):
    if qapp.platformName() != "windows" or len(qapp.screens()) < 2 or not desktop_available():
        pytest.skip("Requires an unlocked Windows desktop with two screens")
    import win32gui

    video = Path("artifacts/v2-media/moving-pattern.mp4").resolve()
    ppt = Path("tests/fixtures/native-animation.pptx").resolve()
    picture = tmp_path / "portrait.png"
    image = QImage(180, 320, QImage.Format.Format_RGB32)
    image.fill(QColor("#224466"))
    image.save(str(picture))
    before = hashlib.sha256(ppt.read_bytes()).hexdigest()
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.show()
    screen = window.monitors.default_audience(window.screen())
    window.monitor_combo.setCurrentIndex(window.monitor_combo.findData(screen.name()))
    entries = window.queue.add([video, ppt, picture])
    entries[0].media_settings = {"volume": 0, "scale": "zoom", "zoom": 400}
    entries[2].media_settings = {"scale": "fill"}
    try:
        window.load_item(entries[0].id)
        qtbot.waitUntil(lambda: window.document is not None and not window.loading, timeout=15000)
        window.start_presentation()
        qtbot.waitUntil(lambda: window.renderer.active and not window.handoff.busy, timeout=15000)
        video_hwnd = window.renderer.native_hwnd
        timer = window.timer._started
        window.load_item(entries[1].id)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[1].id or bool(errors), timeout=40000
        )
        assert not errors and window.renderer.kind == "powerpoint" and window.renderer.active
        assert window.current_slide.view_source is None
        qtbot.waitUntil(
            lambda: not win32gui.IsWindow(video_hwnd) or not win32gui.IsWindowVisible(video_hwnd)
        )
        qtbot.waitUntil(
            lambda: not capture_show(window.renderer.native_hwnd).isNull(), timeout=10000
        )
        window.load_item(entries[2].id)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[2].id and not window.loading, timeout=15000
        )
        assert (
            window.renderer.kind == "image"
            and window.audience.slide.view_settings["scale"] == "fill"
        )
        assert window.presentation.active and window.timer._started == timer
        assert hashlib.sha256(ppt.read_bytes()).hexdigest() == before and not errors
    finally:
        window._project_dirty = False
        window.close()
