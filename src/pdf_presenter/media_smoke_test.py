"""Opt-in frozen runtime verification; uses an isolated data directory and muted audio."""

from __future__ import annotations

import hashlib
import json
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImageReader
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from shiboken6 import isValid

from . import __version__
from .core.project_manager import ProjectManager
from .ui.icons import icon
from .ui.presenter_window import PresenterWindow


def run_media_smoke_test(app, output: Path, source: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "success": False,
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
    }
    errors = []
    window = PresenterWindow(output / "appdata")
    window._warning = errors.append
    app.setQuitOnLastWindowClosed(False)

    def wait_for(predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while not predicate():
            if errors:
                raise AssertionError(errors)
            if time.monotonic() > deadline:
                raise TimeoutError("Media acceptance step timed out")
            QTest.qWait(50)

    def scenario():
        try:
            original = hashlib.sha256(source.read_bytes()).hexdigest()
            report["image_formats"] = sorted(
                bytes(fmt).decode() for fmt in QImageReader.supportedImageFormats()
            )
            resources = Path(__file__).parent / "resources" / "icons"
            for name in ("scene.ico", "scene.png", "chevron-down.svg", "chevron-up.svg"):
                assert (resources / name).is_file(), f"Missing bundled resource: {name}"
            assert not icon("play").pixmap(24, 24).isNull()
            image = output / "image.svg"
            image.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360">'
                '<rect width="640" height="360" fill="#6939c9"/>'
                '<circle cx="320" cy="180" r="100" fill="#40d9be"/></svg>',
                encoding="utf-8",
            )
            entries = window.queue.add([image, source])
            entries[1].media_settings = {"volume": 0}
            window.resize(1440, 900)
            window.show()
            screen = window.monitors.default_audience(window.screen())
            window.monitor_combo.setCurrentIndex(window.monitor_combo.findData(screen.name()))
            window.load_item(entries[0].id)
            wait_for(lambda: window.document is not None and not window.loading)
            wait_for(lambda: not window.current_slide.image.isNull())
            window.start_presentation()
            wait_for(lambda: window.renderer.active and not window.handoff.busy)
            assert window.grab().save(str(output / "image.png"))
            started = window.timer._started
            window.load_item(entries[1].id)
            wait_for(lambda: window.queue.active_id == entries[1].id and not window.handoff.busy)
            backend = window.renderer
            frames = []
            backend.frame_ready.connect(
                lambda frame: frames.append(frame) if len(frames) < 12 else None
            )
            wait_for(lambda: backend.player.position() > 600 and len(frames) > 3)
            assert backend.player.hasVideo() and backend.player.hasAudio()
            assert any(frame != frames[0] for frame in frames[1:]), "Decoded frames did not change"
            assert backend.surface.isVisible() and backend.audio.volume() == 0
            assert window.navigation.media.play.isEnabled()
            window.navigation.media.play.click()
            wait_for(
                lambda: backend.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
            )
            window.navigation.media.seek.setValue(2000)
            wait_for(lambda: abs(backend.player.position() - 2000) < 150)
            # Exercise gain while paused, then mute again before resuming.
            window.navigation.media.volume.setValue(37)
            assert abs(backend.audio.volume() - 0.37) < 0.001
            window.navigation.scale.mode.setCurrentIndex(
                window.navigation.scale.mode.findData("zoom")
            )
            window.navigation.scale.zoom.setValue(200)
            assert window.current_slide.view_settings["zoom"] == 200
            window.project.path = output / "media.pdfpresenter"
            assert window.save_project()
            restored, warning = ProjectManager().load(window.project.path)
            assert not warning and restored.items[1].media_settings["volume"] == 37
            assert restored.items[1].media_settings["zoom"] == 200
            QTest.qWait(150)
            assert window.grab().save(str(output / "player.png"))
            window.navigation.media.volume.setValue(0)
            window.navigation.media.stop.click()
            wait_for(
                lambda: backend.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
            )
            assert window.presentation.active and backend.player.position() == 0
            window.navigation.media.play.click()
            wait_for(lambda: backend.player.position() > 300)
            window.load_item(entries[0].id)
            wait_for(
                lambda: (
                    window.queue.active_id == entries[0].id
                    and not window.loading
                    and not window.handoff.busy
                )
            )
            assert backend.disposed
            assert not isValid(backend.surface) or not backend.surface.isVisible()
            assert window.timer._started == started
            assert hashlib.sha256(source.read_bytes()).hexdigest() == original
            assert not errors
            report.update(
                success=True,
                svg_and_icons=True,
                moving_video=True,
                audio_stream=True,
                pause_seek_stop_restart=True,
                volume=True,
                scale_and_project=True,
                queue="SVG -> video -> SVG",
                timer_preserved=True,
                source_unchanged=True,
                audible_sound="Not checked: test intentionally muted",
            )
        except Exception:
            report["error"] = traceback.format_exc()
        finally:
            window._project_dirty = False
            window.close()
            report["errors"] = errors
            (output / "report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            app.exit(0 if report["success"] else 1)

    QTimer.singleShot(0, scenario)
    return app.exec()
