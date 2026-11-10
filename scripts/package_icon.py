"""Package a supplied PNG as a multi-resolution Windows ICO; no artwork generation."""

import argparse
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage


def package(source: Path, destination: Path):
    image = QImage(str(source))
    if image.isNull():
        raise ValueError("Cannot decode source icon")
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = []
    for size in sizes:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        resized = image.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if not resized.save(buffer, "PNG"):
            raise ValueError("Cannot encode icon image")
        images.append(bytes(buffer.data()))
    offset = 6 + 16 * len(sizes)
    entries = []
    for size, data in zip(sizes, images, strict=True):
        entries.append(
            struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        )
        offset += len(data)
    destination.write_bytes(struct.pack("<HHH", 0, 1, len(sizes)) + b"".join(entries + images))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    package(args.source, args.destination)
