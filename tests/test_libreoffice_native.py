"""Opt-in real Impress/STA/presenter test using an isolated extracted Office profile."""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from pdf_presenter.core.audience_display_manager import AudienceMode
from pdf_presenter.core.backend_manager import EngineAvailability
from pdf_presenter.services import com_worker
from pdf_presenter.ui.presenter_window import PresenterWindow
from pdf_presenter.ui.styles import apply_theme

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("PDFPRESENTER_LIBREOFFICE_NATIVE") != "1",
    reason="Explicit Windows native LibreOffice run required",
)


def _private_profile_sta(pipe, engine):
    """Keep the production worker; resolve only the unregistered test ProgID by CLSID."""
    import win32com.client

    from pdf_presenter.services.com_worker import _sta_loop

    original = win32com.client.Dispatch

    def dispatch(name, *args, **kwargs):
        if name == "com.sun.star.ServiceManager":
            name = "{82154420-0FBF-11d4-8313-005004526AB4}"
        return original(name, *args, **kwargs)

    win32com.client.Dispatch = dispatch
    _sta_loop(pipe, engine)


@pytest.fixture
def private_impress(tmp_path, qtbot, monkeypatch):
    import pythoncom
    import win32com.client
    import win32con
    import win32job
    import win32process

    from pdf_presenter.services.audience_capture import desktop_available
    from pdf_presenter.services.libreoffice_session import LibreOfficeSession
    from pdf_presenter.services.native_window import running_office_pids

    executable = Path(os.environ.get("PDFPRESENTER_LIBREOFFICE", "")).resolve()
    if not executable.is_file():
        pytest.skip("Set PDFPRESENTER_LIBREOFFICE to an extracted/installed soffice.exe")
    if len(QGuiApplication.screens()) < 2 or not desktop_available():
        pytest.skip("Two displays and an interactive Windows desktop are required")
    if running_office_pids("soffice.bin"):
        pytest.skip("Another LibreOffice is running; its profile and processes are left intact")
    job = win32job.CreateJobObject(None, "")
    limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    limits["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
    startup = win32process.STARTUPINFO()
    startup.dwFlags |= win32con.STARTF_USESHOWWINDOW
    startup.wShowWindow = win32con.SW_HIDE
    profile = (tmp_path / "impress-profile").as_uri()
    arguments = [
        str(executable),
        f"-env:UserInstallation={profile}",
        "--nodefault",
        "--nologo",
        "--norestore",
        "--invisible",
    ]
    process = thread = manager = settings = provider = session = None
    pythoncom.CoInitialize()
    try:
        process, thread, _, _ = win32process.CreateProcess(
            str(executable),
            subprocess.list2cmdline(arguments),
            None,
            None,
            False,
            win32con.CREATE_SUSPENDED | win32con.CREATE_NO_WINDOW,
            None,
            None,
            startup,
        )
        try:
            win32job.AssignProcessToJobObject(job, process)
        except Exception:
            win32process.TerminateProcess(process, 1)  # Only our not-yet-started private process.
            raise
        win32process.ResumeThread(thread)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            pythoncom.PumpWaitingMessages()
            try:
                manager = win32com.client.Dispatch("{82154420-0FBF-11d4-8313-005004526AB4}")
                break
            except pythoncom.com_error:
                qtbot.wait(100)
        assert manager is not None, "The isolated LibreOffice COM server did not become available"
        session = LibreOfficeSession()
        session.manager = manager
        provider = manager.createInstance("com.sun.star.configuration.ConfigurationProvider")
        settings = provider.createInstanceWithArguments(
            "com.sun.star.configuration.ConfigurationUpdateAccess",
            (session._property("nodepath", "/org.openoffice.Office.Impress/Misc/Start"),),
        )
        settings.setPropertyValue("EnablePresenterScreen", False)
        settings.commitChanges()  # Only the disposable profile, never the user's preferences.
        monkeypatch.setattr(com_worker, "_sta_loop", _private_profile_sta)
        yield str(executable)
    finally:
        if session is not None:
            session.close()
        session = settings = provider = manager = None
        pythoncom.CoUninitialize()
        job.Close()
        if thread is not None:
            thread.Close()
        if process is not None:
            process.Close()


def test_presenter_impress_queue_restart_media_and_cleanup(
    qtbot, tmp_path, monkeypatch, pdf_factory, private_impress
):
    import win32api
    import win32gui

    from pdf_presenter.services.audience_capture import capture_show

    fixture = Path("tests/fixtures/native-animation.pptx").resolve()
    video = Path("artifacts/v2-media/embedded.pptx").resolve()
    if not fixture.is_file() or not video.is_file():
        pytest.skip("Generate native Office/media fixtures first")
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (fixture, video)}
    output = Path("artifacts/v2-libreoffice-presenter")
    output.mkdir(exist_ok=True)
    report = {"success": False, "engine": "libreoffice", "stages": [], "handoff_samples": []}
    window = PresenterWindow(tmp_path / "appdata")
    qtbot.addWidget(window)
    apply_theme(QApplication.instance())
    window.backend_manager.availability = EngineAvailability(False, private_impress, True)
    errors = []
    monkeypatch.setattr(window, "_warning", errors.append)
    window.show()
    entries = window.queue.add(
        [pdf_factory(3, "before.pdf"), fixture, video, pdf_factory(3, "after.pdf")]
    )
    for item in entries[1:3]:
        item.preferred_backend = "libreoffice"
    sampler = QTimer(window)
    sampler.setInterval(20)

    def sample_cover():
        if not window.handoff.busy or not window.audience.isVisible():
            return
        rect = win32gui.GetWindowRect(int(window.audience.winId()))
        point = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
        top = win32gui.GetAncestor(win32gui.WindowFromPoint(point), 2)
        report["handoff_samples"].append(
            {"covered": top == int(window.audience.winId()), "class": win32gui.GetClassName(top)}
        )

    sampler.timeout.connect(sample_cover)
    sampler.start()

    def open_item(item):
        window.load_item(item.id)
        qtbot.waitUntil(
            lambda: (window.queue.active_id == item.id and not window.loading) or bool(errors),
            timeout=45000,
        )
        assert not errors
        report["stages"].append(item.name)

    try:
        target = window.monitors.default_audience(window.screen())
        window.monitor_combo.setCurrentIndex(window.monitor_combo.findData(target.name()))
        open_item(entries[0])
        window.start_presentation()
        qtbot.waitUntil(
            lambda: window.audience.isVisible() and not window.handoff.busy, timeout=15000
        )
        started = window.timer._started
        entries[1].last_slide = 1
        open_item(entries[1])
        backend = window.renderer
        assert backend.kind == "libreoffice" and backend.active and backend.current == 1
        assert window.timer._started == started
        assert "Speaker note 2" in window.notes_panel.editor.toPlainText()
        monitor = win32api.GetMonitorInfo(win32api.MonitorFromWindow(backend.native_hwnd, 2))
        assert monitor["Device"] == backend.target.native_device
        assert win32gui.GetWindowRect(backend.native_hwnd) == monitor["Monitor"]
        qtbot.wait(500)
        frame = capture_show(backend.native_hwnd)
        assert not frame.isNull()
        frame.save(str(output / "native-slide.png"))
        window.grab().save(str(output / "presenter.png"))
        window.slides.go_to(4)
        qtbot.waitUntil(lambda: window.slides.current == 4 or bool(errors), timeout=10000)
        assert not errors
        for mode in (AudienceMode.BLACK, AudienceMode.WHITE, AudienceMode.SLIDE):
            window.set_audience_mode(mode)
            qtbot.waitUntil(lambda: backend.service.idle, timeout=15000)
        first_hwnd = backend.native_hwnd
        window.presentation.stop()
        qtbot.waitUntil(lambda: not backend.active, timeout=10000)
        assert not win32gui.IsWindow(first_hwnd)
        window.start_presentation()
        qtbot.waitUntil(
            lambda: backend.active and not window.handoff.busy or bool(errors), timeout=25000
        )
        assert not errors and window.slides.current == 0
        restarted = window.timer._started
        open_item(entries[2])
        assert window.renderer.kind == "libreoffice" and window.renderer.active
        assert window.timer._started == restarted
        qtbot.wait(2000)
        first = capture_show(window.renderer.native_hwnd)
        qtbot.wait(750)
        second = capture_show(window.renderer.native_hwnd)
        assert not first.isNull() and not second.isNull() and first != second
        first.save(str(output / "video-first.png"))
        second.save(str(output / "video-second.png"))
        video_hwnd = window.renderer.native_hwnd
        open_item(entries[3])
        assert window.renderer.kind == "pdf" and window.presentation.active
        assert window.timer._started == restarted and not win32gui.IsWindow(video_hwnd)
        assert report["handoff_samples"] and all(
            sample["covered"] for sample in report["handoff_samples"]
        ), report["handoff_samples"]
        for path, digest in hashes.items():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        report.update(success=True, video_pixels_changed=True, sources_unchanged=True)
    finally:
        sampler.stop()
        window._project_dirty = False
        window.close()
        qtbot.waitUntil(lambda: not window.isVisible(), timeout=15000)
        report["worker_closed"] = window.backend_manager.services.finished
        report["errors"] = errors
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    assert report["worker_closed"]
