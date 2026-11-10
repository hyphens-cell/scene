"""Small owned clips for Qt/FFmpeg decoder acceptance; no Office or app packaging."""

import json
import subprocess
from pathlib import Path


def main():
    import imageio_ffmpeg

    directory = Path("artifacts/scene-formats")
    directory.mkdir(exist_ok=True)
    variants = {
        "h264.mp4": ("libx264", "aac"),
        "h265.mp4": ("libx265", "aac"),
        "mpeg4.m4v": ("mpeg4", "aac"),
        "h264.mkv": ("libx264", "aac"),
        "mpeg4.avi": ("mpeg4", "mp3"),
        "h264.mov": ("libx264", "aac"),
        "vp9.webm": ("libvpx-vp9", "libopus"),
        "wmv.wmv": ("wmv2", "wmav2"),
        "wmv.asf": ("wmv2", "wmav2"),
        "mpeg.mpg": ("mpeg2video", "mp2"),
        "mpeg.mpeg": ("mpeg2video", "mp2"),
        "h264.ts": ("libx264", "aac"),
        "h264.mts": ("libx264", "aac"),
        "h264.m2ts": ("libx264", "aac"),
        "dvd.vob": ("mpeg2video", "mp2"),
        "theora.ogv": ("libtheora", "libvorbis"),
        "h264.flv": ("libx264", "aac"),
        "mobile.3gp": ("mpeg4", "aac"),
    }
    report = {}
    for name, (video, audio) in variants.items():
        command = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "2",
            "-c:v",
            video,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            audio,
            "-af",
            "volume=0.01",
        ]
        if name.endswith(".mts"):
            command += ["-f", "mpegts"]
        if video == "libx265":
            command += ["-x265-params", "log-level=error:pools=1"]
        result = subprocess.run(
            command + [str(directory / name)], capture_output=True, text=True, timeout=45
        )
        report[name] = {
            "video": video,
            "audio": audio,
            "created": result.returncode == 0,
            "error": result.stderr.strip(),
        }
        print(name, "OK" if result.returncode == 0 else result.stderr.strip())
    (directory / "generation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-display_rotation",
            "90",
            "-i",
            str(directory / "h264.mp4"),
            "-c",
            "copy",
            str(directory / "portrait.mp4"),
        ],
        check=True,
        timeout=15,
    )


if __name__ == "__main__":
    main()
