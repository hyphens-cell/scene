import os
from pathlib import Path

import pytest

from pdf_presenter.core.backend_manager import BackendManager, EngineAvailability
from pdf_presenter.core.canva_url import is_canva_url, normalize_canva_url
from pdf_presenter.core.presentation_queue import PresentationQueueManager
from pdf_presenter.core.project_manager import EventProject, ProjectManager


def _owned_media_worker(pipe):
    """Run the real WebView2 host/IPC against our own HTML + silent H.264 fixture."""
    import base64

    import webview

    from pdf_presenter.services.canva_worker import run_canva_worker

    clip = Path("artifacts/ppt-loop/moving-pattern.mp4").read_bytes()
    html = (
        '<html><body style="margin:0;background:black">'
        '<video style="width:100vw;height:100vh" autoplay muted src="data:video/mp4;base64,'
        + base64.b64encode(clip).decode()
        + '"></video><footer><div role="slider" aria-label="Design progress" '
        'aria-valuemax="1" aria-valuenow="1"></div></footer></body></html>'
    )
    create = webview.create_window

    def create_fixture(*args, **kwargs):
        kwargs["html"] = html
        window = create(*args, **kwargs)
        window.load_url = lambda _: None  # Test never contacts a website.
        return window

    webview.create_window = create_fixture
    run_canva_worker(pipe)


@pytest.mark.skipif(
    os.environ.get("SCENE_CANVA_NATIVE") != "1", reason="Requires real Windows WebView2"
)
def test_webview_media_controls_with_owned_fixture(qtbot, qapp, tmp_path, pdf_factory, monkeypatch):
    from pdf_presenter.services import canva_service

    if not Path("artifacts/ppt-loop/moving-pattern.mp4").is_file():
        pytest.skip("Generate silent fixtures with make_media_fixture.py --tone-gain 0")
    monkeypatch.setattr(canva_service, "run_canva_worker", _owned_media_worker)
    monkeypatch.setenv("SCENE_CANVA_VIDEO_URL", "https://canva.link/ownedfixture")
    _exercise_canva_video_controls(qtbot, qapp, tmp_path, pdf_factory)


@pytest.mark.parametrize(
    "value",
    [
        "http://canva.com/design/a/b/view",
        "https://canva.com.evil.org/design/a/b/view",
        "https://user:password@canva.com/design/a/b/view",
        "https://canva.com:444/design/a/b/view",
        "file:///C:/secret",
        "https://canva.com/login",
        "https://canva.link/../login",
        "https://canva.com/design/a/b/view\n",
        "https://canva.com/design/a/b/view/evil",
    ],
)
def test_canva_rejects_untrusted_urls(value):
    assert not is_canva_url(value)


def test_canva_queue_project_preserves_url_and_loop(tmp_path):
    value = "https://www.canva.com/design/DEMO/token/edit?utm_source=test"
    expected = "https://www.canva.com/design/DEMO/token/view"
    assert normalize_canva_url(value) == expected
    queue = PresentationQueueManager()
    item = queue.add([value])[0]
    item.media_settings = {"loop": True, "volume": 30}
    assert item.format == "CANVA" and item.path == expected
    assert BackendManager(EngineAvailability()).choose(expected).kind == "canva"
    project = EventProject(items=queue.items)
    path = ProjectManager().save(project, tmp_path / "canva.pdfpresenter")
    loaded, warning = ProjectManager().load(path)
    assert not warning and loaded.items[0].path == expected
    assert loaded.items[0].media_settings["loop"] is True


def test_canva_fatal_error_closes_audio_process_but_clip_error_keeps_show(qapp):
    from unittest.mock import MagicMock

    from pdf_presenter.backends.canva_backend import CanvaBackend
    from pdf_presenter.core.capability_model import PresentationDocument

    backend = CanvaBackend()
    backend.service = MagicMock()
    backend.document = PresentationDocument(
        "https://canva.link/test", "test", 1, "Test", ((1920, 1080),)
    )
    backend.active = True
    backend._poller.start()
    failures = []
    backend.failed.connect(failures.append)
    backend._received("command_error", {"method": "control", "message": "Unsupported video"})
    assert backend.active and backend._poller.isActive()
    backend.service.close.assert_not_called()
    backend._received("command_error", {"method": "navigate", "message": "Viewer unavailable"})
    assert not backend.active and not backend._poller.isActive()
    assert failures == ["Viewer unavailable"]
    backend.service.close.assert_called_once_with(force=True)


def test_canva_missing_runtime_is_actionable(monkeypatch):
    import winreg

    from pdf_presenter.services.webview_runtime import require_webview2

    def missing(*_):
        raise FileNotFoundError()

    monkeypatch.setattr(winreg, "OpenKey", missing)
    with pytest.raises(RuntimeError, match="Справка → WebView2"):
        require_webview2()


def test_canva_can_be_replaced_after_failed_service_is_deleted(qtbot):
    from PySide6.QtCore import QObject, Signal
    from shiboken6 import isValid

    from pdf_presenter.backends.canva_backend import CanvaBackend

    class FailedService(QObject):
        received = Signal(str, object)
        closing = False

        def close(self, *, force=False):
            if not self.closing:
                self.closing = True
                self.deleteLater()

    backend = CanvaBackend()
    backend.service = FailedService()
    backend.service.received.connect(backend._received)
    backend._received("error", "Connection lost")
    qtbot.waitUntil(lambda: not isValid(backend.service))
    backend.dispose()
    assert backend.disposed


def test_loaded_canva_preflight_does_not_claim_missing_file(qtbot, tmp_path):
    from pdf_presenter.core.capability_model import PresentationDocument
    from pdf_presenter.ui.presenter_window import PresenterWindow

    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    item = window.queue.add(["https://canva.link/test"])[0]
    window.queue.activate(item.id)
    window.document = PresentationDocument(item.path, "test", 11, "Canva", ((1920, 1080),) * 11)
    window.preflight_all()
    assert item.slide_count == 11
    assert not any("файл больше не найден" in message for message in item.warnings)
    window._preflight_dialog.close()
    window._project_dirty = False
    window.close()


@pytest.mark.skipif(
    os.environ.get("SCENE_CANVA_NATIVE") != "1" or not os.environ.get("SCENE_CANVA_URLS"),
    reason="Requires WebView2 and public fixture URLs in SCENE_CANVA_URLS (at least 5 slides)",
)
@pytest.mark.parametrize("source", os.environ.get("SCENE_CANVA_URLS", "").split())
def test_live_canva_presenter_navigation_and_cleanup(qtbot, qapp, tmp_path, source):
    from pdf_presenter.ui.presenter_window import PresenterWindow
    from pdf_presenter.ui.styles import apply_theme

    apply_theme(qapp)
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors = []
    window._warning = errors.append
    window.show()
    entry = window.queue.add([source])[0]
    entry.media_settings = {"volume": 0}
    service = None
    try:
        window.load_item(entry.id)
        qtbot.waitUntil(lambda: window.document is not None or bool(errors), timeout=85000)
        assert not errors, errors
        assert window.document.page_count >= 5
        backend = window.renderer
        backend.failed.connect(errors.append)
        service = backend.service
        window.start_presentation()
        qtbot.waitUntil(
            lambda: backend.active and not window.handoff.busy or bool(errors), timeout=25000
        )
        assert not errors, errors
        qtbot.wait(1000)
        window.navigation.next.click()
        qtbot.waitUntil(lambda: backend.current == 1 or bool(errors), timeout=12000)
        assert not errors, errors
        window.slides.go_to_number(5)
        qtbot.waitUntil(lambda: backend.current == 4 or bool(errors), timeout=12000)
        assert not errors, errors
        qtbot.waitUntil(lambda: not backend._preview.isNull(), timeout=10000)
        qtbot.wait(400)
        output = Path("artifacts/canva-native")
        output.mkdir(exist_ok=True)
        window.grab().save(str(output / "presenter.png"))
        window.presentation.toggle_blank("black")
        qtbot.wait(400)
        window.presentation.toggle_blank("black")
        window.presentation.stop()
        qtbot.waitUntil(lambda: not backend.active and not backend.native_hwnd)
    finally:
        window._project_dirty = False
        window.close()
        if service:
            qtbot.waitUntil(lambda: not service.process.is_alive(), timeout=10000)


@pytest.mark.skipif(
    os.environ.get("SCENE_CANVA_NATIVE") != "1" or not os.environ.get("SCENE_CANVA_VIDEO_URL"),
    reason="Requires a confirmed public Canva video fixture in SCENE_CANVA_VIDEO_URL",
)
def test_live_canva_video_controls(qtbot, qapp, tmp_path, pdf_factory):
    _exercise_canva_video_controls(qtbot, qapp, tmp_path, pdf_factory)


def _exercise_canva_video_controls(qtbot, qapp, tmp_path, pdf_factory):
    import json

    from pdf_presenter.core.audience_display_manager import AudienceMode
    from pdf_presenter.ui.presenter_window import PresenterWindow
    from pdf_presenter.ui.styles import apply_theme

    apply_theme(qapp)
    window = PresenterWindow(tmp_path / "data")
    qtbot.addWidget(window)
    errors = []
    window._warning = errors.append
    window.show()
    entries = window.queue.add([os.environ["SCENE_CANVA_VIDEO_URL"], pdf_factory(2)])
    entries[0].media_settings = {"volume": 0}
    service = None
    output = Path("artifacts/canva-native")
    output.mkdir(exist_ok=True)
    seen = []
    try:
        window.load_item(entries[0].id)
        qtbot.waitUntil(lambda: window.document is not None or bool(errors), timeout=85000)
        assert not errors, errors
        backend = window.renderer
        backend.failed.connect(errors.append)
        service = backend.service
        window.start_presentation()
        qtbot.waitUntil(
            lambda: backend.active and not window.handoff.busy or bool(errors), timeout=25000
        )
        assert not errors, errors
        controls = window.navigation.media
        for index in range(window.document.page_count):
            window.slides.go_to(index)
            qtbot.waitUntil(
                lambda index=index: backend.current == index or bool(errors), timeout=12000
            )
            assert not errors, errors
            qtbot.wait(1700)
            seen.append({"page": index + 1, "videos": list(controls.videos)})
            print("Canva video scan:", seen[-1], flush=True)
            if controls.selected and controls.selected["duration"] > 0:
                break
        (output / "video-scan.json").write_text(
            json.dumps(seen, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        assert controls.selected, "No controllable video found in the supplied presentation"
        qtbot.waitUntil(lambda: controls.selected["position"] > 300, timeout=10000)
        first = backend._preview.copy()
        qtbot.wait(700)
        second = backend._preview.copy()
        assert not first.isNull() and not second.isNull() and first != second
        second.save(str(output / "audience-video.png"))
        controls.play.click()
        qtbot.waitUntil(lambda: controls.selected["state"] == 1)
        position = controls.selected["position"]
        qtbot.wait(600)
        assert abs(controls.selected["position"] - position) < 150
        controls.volume.setValue(35)
        qtbot.waitUntil(lambda: controls.selected["volume"] == 35)
        controls.volume.setValue(0)
        qtbot.waitUntil(lambda: controls.selected["volume"] == 0)
        duration = controls.selected["duration"]
        controls.seek.setValue(duration // 2)
        qtbot.waitUntil(lambda: abs(controls.selected["position"] - duration // 2) < 250)
        assert controls.selected["state"] == 1
        if not controls.repeat.isChecked():
            controls.repeat.click()
        qtbot.waitUntil(lambda: controls.selected["loop"])
        controls.play.click()
        qtbot.waitUntil(lambda: controls.selected["state"] == 0)
        for _ in range(2):
            controls.seek.setValue(duration - 600)
            qtbot.waitUntil(lambda: controls.selected["position"] >= duration - 850)
            qtbot.waitUntil(lambda: controls.selected["position"] < 2000, timeout=5000)
        window.set_audience_mode(AudienceMode.BLACK)
        qtbot.waitUntil(lambda: controls.selected["state"] == 1)
        covered = controls.selected["position"]
        qtbot.wait(500)
        assert abs(controls.selected["position"] - covered) < 150
        window.set_audience_mode(AudienceMode.SLIDE)
        qtbot.waitUntil(lambda: controls.selected["state"] == 0)
        controls.stop.click()
        qtbot.waitUntil(
            lambda: controls.selected["state"] == 1 and controls.selected["position"] < 150
        )
        qtbot.wait(500)
        assert controls.selected["position"] < 150
        controls.repeat.click()
        qtbot.waitUntil(lambda: not controls.selected["loop"])
        controls.play.click()
        qtbot.waitUntil(lambda: controls.selected["state"] == 0)
        controls.seek.setValue(duration - 600)
        qtbot.waitUntil(lambda: controls.selected["state"] == 2, timeout=5000)
        window.resize(1024, 768)
        qtbot.wait(500)
        window.grab().save(str(output / "presenter-video-1024.png"))
        assert not errors, errors
        window.load_item(entries[1].id)
        qtbot.waitUntil(
            lambda: window.queue.active_id == entries[1].id and not window.handoff.busy,
            timeout=25000,
        )
        assert window.presentation.active and window.renderer.kind == "pdf"
        qtbot.waitUntil(lambda: not service.process.is_alive(), timeout=10000)
    finally:
        window._project_dirty = False
        window.close()
        if service:
            qtbot.waitUntil(lambda: not service.process.is_alive(), timeout=10000)
