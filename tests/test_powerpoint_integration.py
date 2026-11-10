"""Opt-in: PDFPRESENTER_POWERPOINT_TESTS=1, real Windows/PowerPoint installation."""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtGui import QGuiApplication

from pdf_presenter.backends.powerpoint_com_backend import PowerPointCOMBackend
from pdf_presenter.core.capability_model import DisplayTarget
from pdf_presenter.services.com_worker import OfficeService

pytestmark = pytest.mark.skipif(
    os.environ.get("PDFPRESENTER_POWERPOINT_TESTS") != "1" or sys.platform != "win32",
    reason="Explicit Windows PowerPoint integration run required",
)


def test_powerpoint_video_repeat_and_stop(qtbot, tmp_path):
    from pdf_presenter.services.audience_capture import desktop_available
    from pdf_presenter.ui.presenter_window import PresenterWindow

    if not desktop_available():
        pytest.skip("Requires an unlocked interactive desktop for native PowerPoint media")
    source = Path("artifacts/ppt-loop/on-click.pptx").resolve()
    if not source.is_file():
        pytest.skip("Generate silent fixtures with make_media_fixture.py --tone-gain 0")
    before = source.read_bytes()
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors = []
    window._warning = errors.append
    window.show()
    try:
        window.load_pdf(str(source))
        qtbot.waitUntil(lambda: window.document is not None or bool(errors), timeout=30000)
        assert not errors, errors
        window.start_presentation()
        qtbot.waitUntil(lambda: window.renderer.active and not window.handoff.busy, timeout=30000)
        controls = window.navigation.media
        qtbot.waitUntil(lambda: controls.repeat.isEnabled(), timeout=10000)
        qtbot.wait(1500)
        if controls.repeat.isChecked():
            controls.repeat.click()
            qtbot.waitUntil(lambda: not controls.selected["loop"])
        controls.play.click()
        qtbot.waitUntil(lambda: controls.selected["state"] == 0, timeout=10000)
        duration = controls.selected["duration"]
        controls.seek.setValue(duration - 800)
        qtbot.waitUntil(lambda: controls.selected["state"] == 2, timeout=8000)
        controls.repeat.click()
        qtbot.waitUntil(lambda: controls.selected["loop"])
        controls.play.click()
        qtbot.waitUntil(lambda: controls.selected["state"] == 0, timeout=10000)
        for _ in range(2):
            controls.seek.setValue(duration - 800)
            qtbot.waitUntil(lambda: controls.selected["position"] >= duration - 1000)
            qtbot.waitUntil(lambda: controls.selected["position"] < 2500, timeout=8000)
            assert controls.selected["state"] == 0
        controls.stop.click()
        qtbot.waitUntil(lambda: controls.selected["state"] == 2)
        qtbot.wait(700)
        assert controls.selected["state"] == 2
        assert window.slides.current == 0 and not errors, errors
    finally:
        window._project_dirty = False
        window.close()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=15000)
    assert source.read_bytes() == before


@pytest.fixture(scope="module")
def office_fixture(tmp_path_factory):
    directory = tmp_path_factory.mktemp("office-native")
    subprocess.run(
        [sys.executable, "scripts/make_office_fixture.py", str(directory)], check=True, timeout=40
    )
    return directory


def test_powerpoint_native_animation_preview_notes_and_cleanup(qtbot, office_fixture):
    service = OfficeService("powerpoint")
    backend = PowerPointCOMBackend(service)
    errors, rasters, starts = [], [], []
    backend.load_failed.connect(lambda *args: errors.append(args))
    backend.failed.connect(errors.append)
    backend.ready.connect(lambda *args: rasters.append(args))
    backend.started.connect(lambda: starts.append(True))
    source = office_fixture / "native-animation.pptx"
    before = source.read_bytes()
    try:
        backend.load(str(source))
        qtbot.waitUntil(lambda: backend.document is not None or bool(errors), timeout=50000)
        assert not errors
        assert backend.document.page_count == 5
        assert "Speaker note 2" in backend.document.native_notes[1]
        backend.get_preview(1)
        qtbot.waitUntil(lambda: bool(rasters) or bool(errors), timeout=20000)
        assert not errors and rasters[0][2].samples
        screen = QGuiApplication.screens()[-1]
        area = screen.geometry()
        backend.set_display_target(
            DisplayTarget(
                screen.name(), area.x(), area.y(), area.width(), area.height(), preview=True
            )
        )
        backend.start(1)
        qtbot.waitUntil(lambda: bool(starts) or bool(errors), timeout=25000)
        assert not errors
        assert backend.active and backend.native_hwnd and backend.current == 1
        backend.next()
        qtbot.waitUntil(
            lambda: backend.click_index >= 1 or backend.current != 1 or bool(errors), timeout=10000
        )
        assert not errors
        assert backend.current == 1, "Next must run the animation before advancing the slide"
        backend.next()
        qtbot.waitUntil(lambda: backend.current == 2 or bool(errors), timeout=10000)
        assert not errors
        backend.go_to_slide(0)
        qtbot.waitUntil(lambda: backend.current == 0 or bool(errors), timeout=10000)
        assert not errors
        backend.stop()
        qtbot.waitUntil(lambda: not backend.active, timeout=10000)
        backend.start(3)
        qtbot.waitUntil(lambda: len(starts) == 2 or bool(errors), timeout=25000)
        assert not errors and backend.current == 3
        backend.stop()
        qtbot.waitUntil(lambda: not backend.active, timeout=10000)
    finally:
        backend.dispose()
        service.close()
        qtbot.waitUntil(lambda: service._process is None, timeout=12000)
    assert source.read_bytes() == before


def test_legacy_ppt_can_open_and_render(qtbot, office_fixture):
    service = OfficeService("powerpoint")
    backend = PowerPointCOMBackend(service)
    errors, rasters = [], []
    backend.load_failed.connect(lambda *args: errors.append(args))
    backend.failed.connect(errors.append)
    backend.ready.connect(lambda *args: rasters.append(args))
    try:
        backend.load(str(office_fixture / "legacy.ppt"))
        qtbot.waitUntil(lambda: backend.document is not None or bool(errors), timeout=50000)
        assert not errors and backend.get_slide_count() == 5
        backend.get_preview(0)
        qtbot.waitUntil(lambda: bool(rasters) or bool(errors), timeout=20000)
        assert not errors and rasters[0][2].samples
    finally:
        backend.dispose()
        service.close()
        qtbot.waitUntil(lambda: service._process is None, timeout=12000)


def test_repeated_queue_file_shares_only_owned_document(qtbot, office_fixture):
    service = OfficeService("powerpoint")
    first, second = PowerPointCOMBackend(service), PowerPointCOMBackend(service)
    errors = []
    for backend in (first, second):
        backend.load_failed.connect(lambda *args: errors.append(args))
        backend.failed.connect(errors.append)
    try:
        source = str(office_fixture / "native-animation.pptx")
        first.load(source)
        qtbot.waitUntil(lambda: first.document is not None or bool(errors), timeout=50000)
        screen = QGuiApplication.screens()[-1]
        area = screen.geometry()
        first.set_display_target(
            DisplayTarget(
                screen.name(), area.x(), area.y(), area.width(), area.height(), preview=True
            )
        )
        first.start(0)
        qtbot.waitUntil(lambda: first.active or bool(errors), timeout=25000)
        assert not errors
        second.load(source)
        qtbot.waitUntil(lambda: second.document is not None or bool(errors), timeout=50000)
        assert not errors and second.document.page_count == 5
        first.dispose()
        rasters = []
        second.ready.connect(lambda *args: rasters.append(args))
        second.get_preview(2)
        qtbot.waitUntil(lambda: bool(rasters) or bool(errors), timeout=20000)
        assert not errors and rasters[0][1] == 2
    finally:
        first.dispose()
        second.dispose()
        service.close()
        qtbot.waitUntil(lambda: service._process is None, timeout=12000)


@pytest.mark.parametrize("kind", ["embedded", "linked", "on-click"])
def test_native_video_player_advances(qtbot, kind):
    from pdf_presenter.core.media_inspector import inspect_media

    directory = Path("artifacts/v2-media").resolve()
    source = directory / f"{kind}.pptx"
    if not source.exists():
        pytest.skip("Run scripts/make_media_fixture.py artifacts/v2-media first")
    report = inspect_media(str(source))
    assert report.linked if kind == "linked" else report.embedded
    assert not report.missing
    service = OfficeService("powerpoint")
    backend = PowerPointCOMBackend(service)
    errors, replies = [], {}
    backend.load_failed.connect(lambda *args: errors.append(args))
    backend.failed.connect(errors.append)
    service.completed.connect(lambda _, request, data: replies.update({request: data}))
    before = source.read_bytes()
    try:
        backend.load(str(source))
        qtbot.waitUntil(lambda: backend.document is not None or bool(errors), timeout=50000)
        assert not errors
        screen = QGuiApplication.screens()[-1]
        area = screen.geometry()
        backend.set_display_target(
            DisplayTarget(
                screen.name(),
                area.x(),
                area.y(),
                area.width(),
                area.height(),
                preview=len(QGuiApplication.screens()) < 2,
            )
        )
        backend.start(0)
        qtbot.waitUntil(lambda: backend.active or bool(errors), timeout=25000)
        assert not errors
        if kind == "on-click":
            # A Next during the entry fade finishes that transition. Exercise
            # the media's click trigger after the fixture's transition settles.
            qtbot.wait(2500)
            backend.next()
        deadline = time.monotonic() + 12
        states = []
        while time.monotonic() < deadline:
            request = service.call(backend.document_id, "media_status", priority=0)
            qtbot.waitUntil(
                lambda request=request: request in replies or bool(errors), timeout=10000
            )
            assert not errors
            state = replies.pop(request)
            states.append(state)
            if state and state[0]["state"] == 0 and state[0]["position"] >= 500:
                break
            qtbot.wait(250)
        else:
            pytest.fail(f"Native media clock did not advance: {states}")
        assert backend.current == 0
        backend.stop()  # Deliberately stop while the clip is still playing.
        qtbot.waitUntil(lambda: not backend.active or bool(errors), timeout=12000)
        assert not errors
        assert source.read_bytes() == before
    finally:
        backend.dispose()
        service.close()
        qtbot.waitUntil(lambda: service._process is None, timeout=12000)


def test_preflight_missing_video_warns_without_playback_and_keeps_queue_usable(
    qtbot, pdf_factory, tmp_path, monkeypatch
):
    import zipfile
    from xml.etree import ElementTree as ET

    from pdf_presenter.core.presentation_queue import QueueState
    from pdf_presenter.ui.presenter_window import PresenterWindow

    fixture = Path("artifacts/v2-media/linked.pptx")
    if not fixture.exists():
        pytest.skip("Run scripts/make_media_fixture.py artifacts/v2-media first")
    source = tmp_path / "missing-video.pptx"
    missing = tmp_path / "unavailable-video.mp4"
    changed = 0
    with zipfile.ZipFile(fixture) as original, zipfile.ZipFile(source, "w") as output:
        for part in original.infolist():
            data = original.read(part)
            if part.filename.startswith("ppt/slides/_rels/"):
                root = ET.fromstring(data)
                for relation in root:
                    if relation.get("TargetMode") == "External" and relation.get("Type", "").rsplit(
                        "/", 1
                    )[-1] in {"media", "video"}:
                        relation.set("Target", missing.as_uri())
                        changed += 1
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            output.writestr(part, data)
    assert changed and not missing.exists()
    before = source.read_bytes()
    window = PresenterWindow(tmp_path / "appdata")
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.show()
    entries = window.queue.add([source, pdf_factory(2, "following.pdf")])
    try:
        window.preflight_all()
        qtbot.waitUntil(lambda: not window._preflight_running, timeout=50000)
        assert [item.state for item in entries] == [QueueState.READY, QueueState.READY]
        assert entries[0].slide_count == 2
        assert any(missing.name in warning for warning in entries[0].warnings)
        assert not window.presentation.active and not window.audience.isVisible()
        assert window.preloader.backend is None
        window._preflight_dialog.close()

        window.load_item(entries[0].id)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[0].id or bool(errors), timeout=40000
        )
        assert not errors
        assert window.renderer.kind == "powerpoint"
        assert not window.renderer.active and not window.renderer.native_hwnd
        assert window.start_button.isEnabled()
        assert window.backend_status.warning_button.isEnabled()
        assert any(missing.name in warning for warning in window.queue.active.warnings)
        window.start_presentation()
        qtbot.waitUntil(lambda: window.renderer.active or bool(errors), timeout=25000)
        assert not errors and window.presentation.active
        window.slides.go_to(1)
        qtbot.waitUntil(lambda: window.slides.current == 1 or bool(errors), timeout=10000)
        assert not errors
        started = window.timer._started
        window.adjacent_file(1)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[1].id or bool(errors), timeout=15000
        )
        assert not errors and window.renderer.kind == "pdf"
        assert window.presentation.active and window.timer._started == started
        assert source.read_bytes() == before
    finally:
        window._project_dirty = False
        window.close()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=15000)


def test_native_video_finishes_then_uses_authored_slide_timing(qtbot):
    import hashlib
    import json

    source = Path("artifacts/v2-media-advance/after-video.pptx").resolve()
    if not source.exists():
        pytest.skip("Run scripts/make_media_fixture.py artifacts/v2-media-advance first")
    before = source.read_bytes()
    service = OfficeService("powerpoint")
    backend = PowerPointCOMBackend(service)
    errors, replies, samples = [], {}, []
    backend.load_failed.connect(lambda *args: errors.append(args))
    backend.failed.connect(errors.append)
    service.completed.connect(lambda _, request, data: replies.update({request: data}))
    try:
        backend.load(str(source))
        qtbot.waitUntil(lambda: backend.document is not None or bool(errors), timeout=50000)
        assert not errors
        screen = QGuiApplication.screens()[-1]
        area = screen.geometry()
        backend.set_display_target(
            DisplayTarget(
                screen.name(), area.x(), area.y(), area.width(), area.height(), preview=True
            )
        )
        backend.start(0)
        qtbot.waitUntil(lambda: backend.active or bool(errors), timeout=25000)
        assert not errors
        deadline = time.monotonic() + 40
        while backend.current == 0 and time.monotonic() < deadline:
            request = service.call(backend.document_id, "media_status", priority=0)
            qtbot.waitUntil(
                lambda request=request: request in replies or bool(errors), timeout=10000
            )
            assert not errors
            samples.extend(replies.pop(request))
            qtbot.wait(250)
        assert backend.current == 1, f"Authored transition did not occur: {samples}"
        assert any(sample["state"] == 0 and sample["position"] >= 10500 for sample in samples)
        assert source.read_bytes() == before
        destination = Path("artifacts/v2-video-finish")
        destination.mkdir(exist_ok=True)
        (destination / "report.json").write_text(
            json.dumps(
                {
                    "success": True,
                    "source_sha256": hashlib.sha256(before).hexdigest(),
                    "final_slide_index": backend.current,
                    "samples": samples,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        backend.dispose()
        service.close()
        qtbot.waitUntil(lambda: service._process is None, timeout=12000)


def test_two_screen_pdf_powerpoint_handoff_in_presenter(
    qtbot, office_fixture, pdf_factory, tmp_path, monkeypatch
):
    import win32api
    import win32gui
    from PySide6.QtWidgets import QApplication

    from pdf_presenter.services.audience_capture import desktop_available
    from pdf_presenter.ui.presenter_window import PresenterWindow
    from pdf_presenter.ui.styles import apply_theme

    if len(QGuiApplication.screens()) < 2:
        pytest.skip("Two physical Windows displays are required")
    if not desktop_available():
        pytest.skip("Unlock the Windows desktop to verify actual audience pixels")
    window = PresenterWindow(tmp_path / "data")
    apply_theme(QApplication.instance())
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.show()
    first = pdf_factory(4)
    native = office_fixture / "native-animation.pptx"
    last = pdf_factory(3, "last.pdf")
    entries = window.queue.add([first, native, last])
    try:
        target = window.monitors.default_audience(window.screen())
        window.monitor_combo.setCurrentIndex(window.monitor_combo.findData(target.name()))
        window.load_item(entries[0].id)
        qtbot.waitUntil(lambda: window.document is not None and not window.loading, timeout=20000)
        window.start_presentation()
        qtbot.waitUntil(
            lambda: window.audience.isVisible() and not window.handoff.busy, timeout=15000
        )
        started = window.timer._started
        window.load_item(entries[1].id)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[1].id or bool(errors), timeout=40000
        )
        assert not errors
        assert window.renderer.kind == "powerpoint" and window.renderer.active
        assert window.presentation.active and window.timer._started == started
        hwnd = window.renderer.native_hwnd
        monitor = win32api.GetMonitorInfo(win32api.MonitorFromWindow(hwnd, 2))
        assert win32gui.GetWindowRect(hwnd) == monitor["Monitor"]
        assert monitor["Device"] == window.renderer.target.native_device
        window.slides.go_to(1)
        qtbot.waitUntil(lambda: window.slides.current == 1, timeout=15000)
        assert "Speaker note 2" in window.notes_panel.editor.toPlainText()
        window.slides.next()
        qtbot.waitUntil(lambda: window.renderer.click_index >= 1, timeout=15000)
        assert window.slides.current == 1
        qtbot.waitUntil(
            lambda: (
                not window.current_slide.image.isNull() and not window.next_slide.image.isNull()
            ),
            timeout=20000,
        )
        rect = monitor["Monitor"]
        center = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
        top_window = win32gui.GetAncestor(win32gui.WindowFromPoint(center), 2)
        assert top_window == hwnd, (
            "The native audience surface must actually be on top",
            top_window,
            win32gui.GetClassName(top_window),
            int(window.audience.winId()),
            hwnd,
        )
        # Capture only the monitor verified above to be occupied by our slideshow.
        # grabWindow(hwnd) can return black for Office's GPU-rendered surface.
        captured = []

        def visible_slide():
            from pdf_presenter.services.audience_capture import capture_show

            if win32gui.GetAncestor(win32gui.WindowFromPoint(center), 2) != hwnd:
                return False
            capture = capture_show(hwnd)
            if capture.isNull():
                return False
            samples = [
                capture.pixelColor(
                    x * capture.width() // 10, y * capture.height() // 10
                ).lightness()
                for x in range(1, 10)
                for y in range(1, 10)
            ]
            if samples and max(samples) > 80:
                captured.append(capture)
                return True
            return False

        try:
            qtbot.waitUntil(visible_slide, timeout=8000)
        except Exception:
            print(
                "Native diagnostics:",
                window.renderer.native_state,
                window.renderer.click_index,
                window.renderer.current,
                win32gui.GetClassName(hwnd),
                monitor,
                target.name(),
            )
            raise
        screenshot = captured[-1]
        # The live image must have the same orientation as the exported slide.
        # This catches upside-down GDI captures used by the HOLD audience mode.
        from PySide6.QtCore import Qt

        reference = window.current_slide.image.scaled(96, 54)
        actual = screenshot.scaled(96, 54)

        def image_error(image):
            return sum(
                abs(image.pixelColor(x, y).lightness() - reference.pixelColor(x, y).lightness())
                for x in range(96)
                for y in range(54)
            )

        assert image_error(actual) < image_error(actual.flipped(Qt.Orientation.Vertical))
        screenshots = Path("artifacts/v2-native")
        screenshots.mkdir(parents=True, exist_ok=True)
        screenshot.save(str(screenshots / "powerpoint-audience.png"))
        window.grab().save(str(screenshots / "presenter.png"))
        # Real low-level hook: send shortcuts only while our slideshow owns focus.
        import win32con

        def native_key(key):
            assert win32gui.GetAncestor(win32gui.GetForegroundWindow(), 2) == hwnd
            win32api.keybd_event(key, 0, 0, 0)
            win32api.keybd_event(key, 0, win32con.KEYEVENTF_KEYUP, 0)

        win32gui.SetForegroundWindow(hwnd)
        qtbot.waitUntil(lambda: win32gui.GetForegroundWindow() == hwnd, timeout=3000)
        native_key(win32con.VK_END)
        qtbot.waitUntil(lambda: window.slides.current == 4, timeout=10000)
        native_key(0x32)  # 2 + Enter returns to slide 2; the number stays private.
        native_key(win32con.VK_RETURN)
        qtbot.waitUntil(lambda: window.slides.current == 1, timeout=10000)
        window.load_item(entries[2].id)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[2].id or bool(errors), timeout=30000
        )
        assert not errors and window.renderer.kind == "pdf"
        assert window.presentation.active and window.timer._started == started
        assert window.audience.isVisible() and not window.audience.preview
        qtbot.waitUntil(lambda: not win32gui.IsWindow(hwnd), timeout=10000)
        window.load_item(entries[1].id)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[1].id or bool(errors), timeout=30000
        )
        assert not errors and window.slides.current == 1
    finally:
        window._project_dirty = False
        window.close()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=15000)


def test_presenter_button_starts_click_video_without_advancing_slide(qtbot, tmp_path, monkeypatch):
    import json

    from PySide6.QtCore import Qt

    from pdf_presenter.core.audience_display_manager import AudienceMode
    from pdf_presenter.services.audience_capture import capture_show, desktop_available
    from pdf_presenter.ui.presenter_window import PresenterWindow

    if len(QGuiApplication.screens()) < 2 or not desktop_available():
        pytest.skip("Two displays and an interactive Windows desktop are required")
    source = Path("artifacts/v2-media/on-click.pptx").resolve()
    if not source.exists():
        pytest.skip("Generate native media fixtures first")
    before = source.read_bytes()
    output = Path("artifacts/v2-video-button")
    output.mkdir(exist_ok=True)
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors, replies = [], {}
    monkeypatch.setattr(window, "_warning", errors.append)
    window.show()
    item = window.queue.add([source])[0]
    try:
        target = window.monitors.default_audience(window.screen())
        window.monitor_combo.setCurrentIndex(window.monitor_combo.findData(target.name()))
        window.load_item(item.id)
        qtbot.waitUntil(lambda: window.document is not None and not window.loading, timeout=40000)
        assert not window.navigation.play_video.isEnabled()
        window.start_presentation()
        qtbot.waitUntil(lambda: window.navigation.play_video.isEnabled(), timeout=30000)
        backend = window.renderer
        backend.service.completed.connect(lambda _, request, data: replies.update({request: data}))

        def media_status():
            request = backend.service.call(backend.document_id, "media_status", priority=0)
            qtbot.waitUntil(lambda: request in replies, timeout=10000)
            return replies.pop(request)

        qtbot.wait(2500)  # The authored fade must settle before checking the click-only video.
        initial = media_status()
        assert initial and initial[0]["position"] == 0
        started = window.timer._started
        window.grab().save(str(output / "presenter.png"))
        qtbot.mouseClick(window.navigation.play_video, Qt.MouseButton.LeftButton)
        states = []
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            state = media_status()
            states.append(state)
            if state and state[0]["state"] == 0 and state[0]["position"] >= 600:
                break
            qtbot.wait(200)
        else:
            pytest.fail(f"Video did not start from the presenter button: {states}")
        first = capture_show(backend.native_hwnd)
        qtbot.wait(700)
        second = capture_show(backend.native_hwnd)
        assert not first.isNull() and not second.isNull() and first != second
        first.save(str(output / "video-first.png"))
        second.save(str(output / "video-second.png"))
        assert window.slides.current == 0 and window.timer._started == started
        controls = window.navigation.media
        qtbot.waitUntil(lambda: controls.play.text() == "Пауза", timeout=10000)
        qtbot.mouseClick(controls.play, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: controls.selected["state"] == 1, timeout=10000)
        paused = media_status()[0]["position"]
        qtbot.wait(600)
        assert abs(media_status()[0]["position"] - paused) < 150
        controls.seek.setValue(7000)
        qtbot.waitUntil(lambda: abs(controls.selected["position"] - 7000) < 250, timeout=10000)
        assert controls.selected["state"] == 1, "Seeking a paused clip must preserve pause"
        qtbot.mouseClick(controls.play, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: controls.selected["state"] == 0, timeout=10000)
        qtbot.mouseClick(controls.stop, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: controls.selected["state"] == 2, timeout=10000)
        assert window.slides.current == 0 and window.timer._started == started
        window.set_audience_mode(AudienceMode.BLACK)
        assert not window.navigation.play_video.isEnabled()
        window.set_audience_mode(AudienceMode.SLIDE)
        window.slides.go_to(1)
        qtbot.waitUntil(lambda: window.slides.current == 1, timeout=15000)
        qtbot.waitUntil(lambda: not window.navigation.play_video.isEnabled(), timeout=10000)
        window.play_video()  # Direct API failure also remains recoverable.
        qtbot.waitUntil(lambda: "нет видео" in window.statusBar().currentMessage(), timeout=10000)
        assert window.presentation.active and backend.active and window.slides.current == 1
        assert window.timer._started == started and not errors
        (output / "report.json").write_text(
            json.dumps(
                {
                    "success": True,
                    "initial": initial,
                    "playing": states,
                    "changing_pixels": True,
                    "timer_preserved": True,
                    "no_video_keeps_show": True,
                    "pause_seek_resume_stop": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        window._project_dirty = False
        window.close()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=15000)
    assert source.read_bytes() == before


def test_powerpoint_to_powerpoint_handoff_during_video(qtbot, tmp_path, monkeypatch):
    import win32gui

    from pdf_presenter.core.audience_display_manager import AudienceMode
    from pdf_presenter.services.audience_capture import capture_show, desktop_available
    from pdf_presenter.ui.presenter_window import PresenterWindow

    if len(QGuiApplication.screens()) < 2 or not desktop_available():
        pytest.skip("Two displays and an interactive Windows desktop are required")
    directory = Path("artifacts/v2-media").resolve()
    paths = [directory / "embedded.pptx", directory / "linked.pptx"]
    if not all(path.exists() for path in paths):
        pytest.skip("Generate native media fixtures first")
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.show()
    entries = window.queue.add(paths)
    captures = Path("artifacts/v2-native-video")
    captures.mkdir(exist_ok=True)

    def wait_for_video(backend):
        replies = {}

        def completed(_, request, data):
            replies[request] = data

        backend.service.completed.connect(completed)
        try:
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                request = backend.service.call(backend.document_id, "media_status", priority=0)
                qtbot.waitUntil(
                    lambda request=request: request in replies or bool(errors), timeout=10000
                )
                assert not errors
                state = replies.pop(request)
                if state and state[0]["state"] == 0 and state[0]["position"] >= 500:
                    return
                qtbot.wait(250)
            pytest.fail("Native video failed to start during queue handoff")
        finally:
            backend.service.completed.disconnect(completed)

    try:
        target = window.monitors.default_audience(window.screen())
        window.monitor_combo.setCurrentIndex(window.monitor_combo.findData(target.name()))
        window.load_item(entries[0].id)
        qtbot.waitUntil(lambda: window.document is not None and not window.loading, timeout=30000)
        window.start_presentation()
        qtbot.waitUntil(lambda: window.renderer.active and not window.handoff.busy, timeout=30000)
        started = window.timer._started
        wait_for_video(window.renderer)
        first_hwnd = window.renderer.native_hwnd
        first_frame = capture_show(first_hwnd)
        assert not first_frame.isNull()
        first_frame.save(str(captures / "embedded.png"))
        qtbot.wait(500)
        later = capture_show(first_hwnd)
        assert not later.isNull() and later != first_frame, "Video pixels must actually change"
        window.set_audience_mode(AudienceMode.HOLD)
        held = window.audience_display.last_image.copy()
        assert not held.isNull()
        held.save(str(captures / "held.png"))
        qtbot.wait(350)
        assert window.audience_display.last_image == held
        window.set_audience_mode(AudienceMode.SLIDE)
        window.load_item(entries[1].id)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[1].id or bool(errors), timeout=40000
        )
        assert not errors and window.renderer.kind == "powerpoint"
        assert window.presentation.active and window.timer._started == started
        wait_for_video(window.renderer)
        assert not win32gui.IsWindow(first_hwnd)
        frame = capture_show(window.renderer.native_hwnd)
        assert not frame.isNull()
        frame.save(str(captures / "linked.png"))
    finally:
        window._project_dirty = False
        window.close()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=15000)
