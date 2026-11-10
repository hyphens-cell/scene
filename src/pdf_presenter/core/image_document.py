"""Image decoding/scaling in the same isolated worker used for PDF rendering."""

import hashlib
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader, QPainter

from pdf_presenter.i18n import tr

from .pdf_document import DocumentError, PdfDocument


def open_image(path: str):
    source = Path(path).resolve()
    with source.open("rb") as stream:
        fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
    reader = QImageReader(str(source))
    reader.setAllocationLimit(256)
    reader.setAutoTransform(True)
    if not reader.canRead():
        raise DocumentError(tr("Не удалось открыть изображение: {p0}", p0=reader.errorString()))
    image = reader.read()
    if image.isNull():
        raise DocumentError(
            tr("Не удалось декодировать изображение: {p0}", p0=reader.errorString())
        )
    warnings = (
        (
            tr(
                "Многостраничное или анимированное изображение: показан первый кадр. Для движения добавьте видео."
            ),
        )
        if reader.imageCount() > 1 or reader.supportsAnimation()
        else ()
    )
    metadata = PdfDocument(
        str(source),
        fingerprint,
        1,
        source.name,
        ((float(image.width()), float(image.height())),),
        warnings,
    )
    return metadata, image


def render_image(image: QImage, key):
    from .render_service import Raster

    _, width, height = key
    scaled = image.scaled(
        width,
        height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QImage(scaled.size(), QImage.Format.Format_RGB888)
    canvas.fill(Qt.GlobalColor.black)
    painter = QPainter(canvas)
    painter.drawImage(0, 0, scaled)
    painter.end()
    return Raster(canvas.width(), canvas.height(), canvas.bytesPerLine(), bytes(canvas.constBits()))
