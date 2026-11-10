"""Candidate file types. Every file is still validated by its actual decoder."""

from PySide6.QtGui import QImageReader

from pdf_presenter.i18n import tr

PRESENTATIONS = {".pdf", ".pptx", ".ppt"}
IMAGES = {
    "." + bytes(value).decode("ascii").lower() for value in QImageReader.supportedImageFormats()
} - {".pdf"}
VIDEOS = {
    ".mp4",
    ".m4v",
    ".mkv",
    ".avi",
    ".mov",
    ".webm",
    ".wmv",
    ".asf",
    ".mpeg",
    ".mpg",
    ".mpe",
    ".ts",
    ".mts",
    ".m2ts",
    ".vob",
    ".ogv",
    ".flv",
    ".3gp",
}
SUPPORTED = PRESENTATIONS | IMAGES | VIDEOS


def file_filter() -> str:
    def patterns(values):
        return " ".join("*" + suffix for suffix in sorted(values))

    return tr(
        "Все материалы ({p0});;Презентации ({p1});;Изображения ({p2});;Видео ({p3});;Все файлы (*)",
        p0=patterns(SUPPORTED),
        p1=patterns(PRESENTATIONS),
        p2=patterns(IMAGES),
        p3=patterns(VIDEOS),
    )
