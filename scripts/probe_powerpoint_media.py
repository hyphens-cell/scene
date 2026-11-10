"""Capture only our native test slideshow and inspect each player property."""

import argparse
import json
import sys
import time
from pathlib import Path


def main(play=False, source=None, output=None, duration=4):
    import pythoncom
    import win32api
    import win32con
    import win32gui
    from PySide6.QtWidgets import QApplication

    from pdf_presenter.core.capability_model import DisplayTarget
    from pdf_presenter.services.audience_capture import capture_show, desktop_available
    from pdf_presenter.services.powerpoint_session import PowerPointSession

    app = QApplication([])
    root = Path(__file__).resolve().parent.parent
    directory = Path(output).resolve() if output else root / "artifacts/v2-media-probe"
    source = Path(source).resolve() if source else root / "artifacts/v2-media/embedded.pptx"
    directory.mkdir(exist_ok=True)
    sys.path.insert(0, str(root / "artifacts/tooling/audio-diagnostics"))
    from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

    speakers = AudioUtilities.GetSpeakers()
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    session = PowerPointSession()
    report = {"desktop_available": desktop_available(), "source": str(source), "samples": []}
    report["audio_output"] = {
        "name": speakers.FriendlyName,
        "muted": bool(speakers.EndpointVolume.GetMute()),
        "volume": speakers.EndpointVolume.GetMasterVolumeLevelScalar(),
    }
    try:
        if not report["desktop_available"]:
            raise RuntimeError("Unlock the interactive desktop before the playback test")
        session.load("media", str(source))
        monitor = next(
            info
            for handle, _, _ in win32api.EnumDisplayMonitors()
            if not (info := win32api.GetMonitorInfo(handle))["Flags"] & 1
        )
        x, y, right, bottom = monitor["Monitor"]
        target = DisplayTarget(
            monitor["Device"], x, y, right - x, bottom - y, native_device=monitor["Device"]
        )
        state = session.start("media", 0, target)
        hwnd = state["hwnd"]
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 0x13)
        for index in range(int(duration * 2)):
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                pythoncom.PumpWaitingMessages()
                app.processEvents()
                time.sleep(0.02)
            player = session.shows["media"].View.Player(3)
            if play and index == 2:
                try:
                    player.Play()
                    report["explicit_play"] = "ok"
                except Exception as exc:
                    report["explicit_play"] = repr(exc)
            sample = {"show": session.status("media")}
            sample["audio"] = []
            for audio in AudioUtilities.GetAllSessions():
                if audio.Process and audio.Process.name().lower() == "powerpnt.exe":
                    meter = audio._ctl.QueryInterface(IAudioMeterInformation)
                    volume = audio.SimpleAudioVolume
                    sample["audio"].append(
                        {
                            "peak": meter.GetPeakValue(),
                            "muted": bool(volume.GetMute()),
                            "volume": volume.GetMasterVolume(),
                        }
                    )
            for name in ("State", "CurrentPosition"):
                try:
                    sample[name] = getattr(player, name)
                except Exception as exc:
                    sample[name] = repr(exc)
            report["samples"].append(sample)
            frame = capture_show(hwnd)
            if not frame.isNull():
                frame.save(str(directory / f"frame-{index}.png"))
    finally:
        session.close()
        pythoncom.CoUninitialize()
        (directory / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--play", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duration", type=float, default=4)
    args = parser.parse_args()
    if not 1 <= args.duration <= 30:
        parser.error("duration must be between 1 and 30 seconds")
    main(args.play, args.source, args.output, args.duration)
