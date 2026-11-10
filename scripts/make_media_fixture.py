"""Generate our own moving H.264/AAC test clip and native PowerPoint decks."""

import argparse
import subprocess
from pathlib import Path


def create(directory: Path, tone_gain: float = 0.06) -> None:
    import imageio_ffmpeg
    import pythoncom
    import win32com.client

    from pdf_presenter.services.native_window import running_office_pids

    if not 0 <= tone_gain <= 1:
        raise ValueError("Tone gain must be between 0 and 1 (0 produces a silent test clip)")
    directory.mkdir(parents=True, exist_ok=True)
    clip = directory / "moving-pattern.mp4"
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=640x360:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "12",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-af",
            f"volume={tone_gain}",
            "-movflags",
            "+faststart",
            str(clip),
        ],
        check=True,
        timeout=45,
    )
    previous = running_office_pids("POWERPNT.EXE")
    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    app = presentation = None
    try:
        app = win32com.client.DispatchEx("PowerPoint.Application")
        for kind in ("embedded", "linked", "on-click", "after-video"):
            presentation = app.Presentations.Add(0)
            slide = presentation.Slides.Add(1, 12)
            title = slide.Shapes.AddTextbox(1, 30, 10, 650, 60)
            title.TextFrame.TextRange.Text = f"Native video: {kind} / test tone"
            title.TextFrame.TextRange.Font.Size = 24
            media = slide.Shapes.AddMediaObject2(
                str(clip),
                -1 if kind == "linked" else 0,
                0 if kind == "linked" else -1,
                40,
                90,
                640,
                360,
            )
            settings = media.AnimationSettings.PlaySettings
            settings.LoopUntilStopped = 0 if kind == "after-video" else -1
            sequence = slide.TimeLine.MainSequence
            while sequence.Count:
                sequence.Item(1).Delete()
            # AddMediaObject2 already creates a click effect. Explicitly replace
            # it; the legacy PlayOnEntry flag alone does not change OOXML timing.
            sequence.AddEffect(media, 83, 0, 1 if kind == "on-click" else 2)
            slide.SlideShowTransition.EntryEffect = 1793  # fade
            if kind == "after-video":
                # Author a timed transition after the 12-second clip. The app
                # must preserve this setting and observe the native transition.
                slide.SlideShowTransition.AdvanceOnClick = 0
                slide.SlideShowTransition.AdvanceOnTime = -1
                slide.SlideShowTransition.AdvanceTime = 13
                presentation.SlideShowSettings.AdvanceMode = 2  # use slide timings
            second = presentation.Slides.Add(2, 12)
            second.Shapes.AddTextbox(
                1, 40, 80, 600, 100
            ).TextFrame.TextRange.Text = "Playback finished"
            presentation.SaveAs(str(directory / f"{kind}.pptx"), 24)
            presentation.Saved = -1
            presentation.Close()
            presentation = None
    finally:
        if presentation is not None:
            presentation.Saved = -1
            presentation.Close()
        if app is not None and not previous and app.Presentations.Count == 0:
            app.Quit()
        app = presentation = None
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--tone-gain", type=float, default=0.06)
    args = parser.parse_args()
    create(args.directory.resolve(), args.tone_gain)
