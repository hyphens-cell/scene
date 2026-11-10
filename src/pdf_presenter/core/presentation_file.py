"""Reject renamed/non-presentation files before Office's permissive import filters."""

from pathlib import Path
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile, ZipFile

from pdf_presenter.i18n import tr

from .media_inspector import _xml

COMPOUND_HEADER = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def validate_presentation_file(path: Path) -> None:
    with path.open("rb") as stream:
        header = stream.read(8)
    if path.suffix.lower() == ".ppt":
        if header != COMPOUND_HEADER:
            raise RuntimeError(tr("Файл PPT повреждён или содержит данные другого формата."))
        return
    if path.suffix.lower() != ".pptx":
        raise RuntimeError(tr("Ожидается презентация PPTX или PPT."))
    if header == COMPOUND_HEADER:
        raise RuntimeError(
            tr(
                "PPTX защищён паролем. Откройте его в PowerPoint или LibreOffice и сохраните незашифрованную копию для мероприятия."
            )
        )
    try:
        with ZipFile(path) as archive:
            if len(archive.namelist()) > 30000:
                raise ValueError(tr("Слишком много частей PPTX"))
            types = _xml(archive, "[Content_Types].xml")
            root = _xml(archive, "ppt/presentation.xml")
            valid_type = any(
                element.get("PartName") == "/ppt/presentation.xml"
                and element.get("ContentType", "").endswith("presentation.main+xml")
                for element in types
            )
            if not valid_type or root.tag.rsplit("}", 1)[-1] != "presentation":
                raise ValueError(tr("Архив не содержит структуру презентации"))
    except (BadZipFile, KeyError, ValueError, ParseError) as exc:
        raise RuntimeError(
            tr("Файл PPTX повреждён или не является презентацией: {p0}", p0=exc)
        ) from exc
