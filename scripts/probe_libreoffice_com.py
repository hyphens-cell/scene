"""Test an extracted LibreOffice COM server with an isolated profile, no registry edits."""

import argparse
import json
import subprocess
import time
import traceback
from pathlib import Path


def main(native=False, media=False):
    import pythoncom
    import win32api
    import win32com.client
    import win32con
    import win32gui
    import win32job
    import win32process

    from pdf_presenter.core.capability_model import DisplayTarget
    from pdf_presenter.services.audience_capture import capture_show, desktop_available
    from pdf_presenter.services.libreoffice_session import LibreOfficeSession
    from pdf_presenter.services.native_window import running_office_pids

    root = Path(__file__).resolve().parent.parent
    directory = root / "artifacts/v2-libreoffice-native"
    directory.mkdir(exist_ok=True)
    executable = root / "artifacts/tooling/libreoffice-26.2.6/program/soffice.exe"
    if running_office_pids("soffice.bin"):
        raise RuntimeError("Another LibreOffice process is running; no changes made")
    job = win32job.CreateJobObject(None, "")
    limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
    limits["BasicLimitInformation"]["LimitFlags"] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
    startup = win32process.STARTUPINFO()
    startup.dwFlags |= win32con.STARTF_USESHOWWINDOW
    startup.wShowWindow = win32con.SW_HIDE
    arguments = [
        str(executable),
        f"-env:UserInstallation={(directory / 'profile').as_uri()}",
        "--nodefault",
        "--nologo",
        "--norestore",
        "--invisible",
    ]
    process = thread = session = None
    report = {
        "success": False,
        "native_requested": native,
        "desktop_available": desktop_available(),
    }
    if native and not report["desktop_available"]:
        job.Close()
        raise RuntimeError("An unlocked interactive desktop is required for the native probe")

    def settle(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            pythoncom.PumpWaitingMessages()
            time.sleep(0.03)

    def snapshot(state, name, delay=1.0):
        hwnd = state["hwnd"]
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )
        settle(delay)
        frame = capture_show(hwnd)
        if frame.isNull():
            raise RuntimeError("Own native slideshow is not available for an unobstructed capture")
        assert frame.save(str(directory / f"{name}.png"))
        return frame

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
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
            win32process.TerminateProcess(process, 1)
            raise
        win32process.ResumeThread(thread)
        manager = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            pythoncom.PumpWaitingMessages()
            try:
                # CLSID read from the signed LibreOffice MSI's Registry table.
                manager = win32com.client.Dispatch("{82154420-0FBF-11d4-8313-005004526AB4}")
                break
            except pythoncom.com_error:
                time.sleep(0.2)
        if manager is None:
            raise RuntimeError(
                "COM server requires installation registration; no registry changes attempted"
            )
        session = LibreOfficeSession()
        original_windows = session._windows

        def diagnosed_windows():
            handles = original_windows()
            pids = running_office_pids("soffice.bin")
            report["pids"] = list(pids)
            owned = []

            def visit(hwnd, _):
                if win32process.GetWindowThreadProcessId(hwnd)[1] in pids:
                    owned.append(
                        {
                            "hwnd": hwnd,
                            "class": win32gui.GetClassName(hwnd),
                            "visible": bool(win32gui.IsWindowVisible(hwnd)),
                            "title": win32gui.GetWindowText(hwnd),
                            "rect": win32gui.GetWindowRect(hwnd),
                        }
                    )

            win32gui.EnumWindows(visit, None)
            report["last_windows"] = owned
            return handles

        session._windows = diagnosed_windows
        session.manager = manager
        session.desktop = manager.createInstance("com.sun.star.frame.Desktop")
        session.owned_application = True
        source = root / "tests/fixtures/native-animation.pptx"
        document = session.load("fixture", str(source))
        preview = session.preview("fixture", 1, 960, 600)
        report.update(
            success=True,
            slides=document.page_count,
            notes=list(document.native_notes),
            preview=[preview.width, preview.height],
        )
        assert (preview.width, preview.height) == (960, 540)
        thumbnail = session.preview("fixture", 1, 300, 188)
        report["thumbnail"] = [thumbnail.width, thumbnail.height]
        assert (thumbnail.width, thumbnail.height) == (300, 169)
        if native:
            # This profile belongs only to this probe; the user's LibreOffice
            # preferences are never changed by the application or this test.
            provider = manager.createInstance("com.sun.star.configuration.ConfigurationProvider")
            settings = provider.createInstanceWithArguments(
                "com.sun.star.configuration.ConfigurationUpdateAccess",
                (session._property("nodepath", "/org.openoffice.Office.Impress/Misc/Start"),),
            )
            settings.setPropertyValue("EnablePresenterScreen", False)
            settings.commitChanges()
            monitors = [
                win32api.GetMonitorInfo(monitor) for monitor, _, _ in win32api.EnumDisplayMonitors()
            ]
            if len(monitors) < 2:
                raise RuntimeError("Two physical displays required for this native test")
            monitor = next(item for item in monitors if not item["Flags"] & 1)
            x, y, right, bottom = monitor["Monitor"]
            target = DisplayTarget(
                monitor["Device"], x, y, right - x, bottom - y, native_device=monitor["Device"]
            )
            state = session.start("fixture", 1, target)
            assert state["active"] and state["index"] == 1, state
            assert win32gui.GetWindowRect(state["hwnd"]) == monitor["Monitor"]
            report["native_start"] = state
            snapshot(state, "native-start")
            report["native_next"] = session.next("fixture")
            report["native_goto_last"] = session.go_to("fixture", 4)
            assert report["native_goto_last"]["index"] == 4
            session.blank("fixture", "black")
            black = snapshot(state, "native-black").scaled(32, 18)
            assert sum(black.pixelColor(16, 9).getRgb()[:3]) < 24
            session.blank("fixture", "white")
            white = snapshot(state, "native-white").scaled(32, 18)
            assert sum(white.pixelColor(16, 9).getRgb()[:3]) > 735
            session.blank("fixture", "")
            session.stop("fixture")
            assert not win32gui.IsWindow(state["hwnd"])
            report["native_restart"] = session.start("fixture", 0, target)
            assert report["native_restart"]["index"] == 0
            snapshot(report["native_restart"], "native-restart")
            session.stop("fixture")
            if media:
                report["media"] = {}
                for kind in ("embedded", "linked", "on-click"):
                    media_source = root / f"artifacts/v2-media/{kind}.pptx"
                    before = media_source.read_bytes()
                    key = f"media-{kind}"
                    session.load(key, str(media_source))
                    state = session.start(key, 0, target)
                    settle(3)
                    if kind == "on-click":
                        session.next(key)
                    first = snapshot(state, key + "-first", delay=2)
                    second = snapshot(state, key + "-second", delay=0.75)
                    area = (
                        first.width() // 5,
                        first.height() // 3,
                        first.width() * 3 // 5,
                        first.height() // 2,
                    )
                    first_region, second_region = first.copy(*area), second.copy(*area)
                    first_pixels = first_region.constBits().tobytes()
                    second_pixels = second_region.constBits().tobytes()
                    samples = range(0, len(first_pixels), 64)
                    changed = sum(
                        first_pixels[n : n + 4] != second_pixels[n : n + 4] for n in samples
                    ) / len(samples)
                    report["media"][kind] = {
                        "state": session.status(key),
                        "changed_fraction": changed,
                        "motion_detected": changed > 0.01,
                    }
                    session.stop(key)
                    session.dispose(key)
                    assert media_source.read_bytes() == before
    except Exception as exc:
        report["success"] = False
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        raise
    finally:
        try:
            if session is not None:
                session.close()
        except Exception as exc:
            report.update(success=False, cleanup_error=str(exc))
        session = None
        pythoncom.CoUninitialize()
        job.Close()  # Only the dedicated, private-profile test process and its children.
        if thread is not None:
            thread.Close()
        if process is not None:
            process.Close()
        (directory / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--media", action="store_true")
    args = parser.parse_args()
    main(args.native or args.media, args.media)
