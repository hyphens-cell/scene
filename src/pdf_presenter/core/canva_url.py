"""Canva links are URLs, never local paths or arbitrary browser destinations."""

import re
from urllib.parse import urlsplit, urlunsplit

from pdf_presenter.i18n import tr


def normalize_canva_url(value: str) -> str:
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 for c in value):
        raise ValueError(tr("Некорректная ссылка Canva."))
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError(tr("Нужна HTTPS-ссылка Canva без логина и пароля в адресе."))
    host = (parsed.hostname or "").lower()
    if host == "canva.link" and re.fullmatch(r"/[A-Za-z0-9]+/?", parsed.path):
        return urlunsplit(("https", host, parsed.path.rstrip("/"), "", ""))
    if host in {"canva.com", "www.canva.com"} and re.fullmatch(
        r"/design/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/(view|edit)/?", parsed.path
    ):
        path = parsed.path.rstrip("/").removesuffix("/edit")
        if not path.endswith("/view"):
            path += "/view"
        return urlunsplit(("https", "www.canva.com", path, "", ""))
    raise ValueError(
        tr("Вставьте ссылку canva.link или ссылку на просмотр дизайна canva.com/design/…")
    )


def is_canva_url(value: str) -> bool:
    try:
        normalize_canva_url(value)
        return True
    except (ValueError, TypeError):
        return False
