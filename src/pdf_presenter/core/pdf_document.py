"""PDF operations live only in the renderer process (or isolated unit tests)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from pdf_presenter.i18n import tr


class DocumentError(Exception):
    """Unreadable, empty or unsupported PDF."""


class PasswordRequired(DocumentError):
    """PDF needs a password, or the supplied password is incorrect."""


@dataclass(frozen=True)
class PdfDocument:
    path: str
    fingerprint: str
    page_count: int
    title: str
    page_sizes: tuple[tuple[float, float], ...]
    warnings: tuple[str, ...] = ()


def open_pdf(path: str, password: str = "") -> tuple[PdfDocument, pymupdf.Document]:
    document = None
    try:
        file = Path(path).resolve()
        with file.open("rb") as stream:
            fingerprint = hashlib.file_digest(stream, "sha256").hexdigest()
        document = pymupdf.open(file)
        if not document.is_pdf:
            raise DocumentError(tr("Выбранный файл не является PDF."))
        if document.needs_pass and not document.authenticate(password):
            raise PasswordRequired(tr("Введите пароль PDF. Предыдущий пароль мог быть неверным."))
        if not document.page_count:
            raise DocumentError(tr("PDF не содержит страниц."))
        sizes = tuple((page.rect.width, page.rect.height) for page in document)
        info = PdfDocument(
            str(file),
            fingerprint,
            document.page_count,
            document.metadata.get("title") or file.name,
            sizes,
        )
        return info, document
    except Exception as exc:
        if document is not None:
            document.close()
        if isinstance(exc, DocumentError):
            raise
        raise DocumentError(tr("Не удалось открыть PDF: {p0}", p0=exc)) from exc
