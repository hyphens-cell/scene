from pdf_presenter.i18n import tr

from ..core.media_formats import IMAGES, VIDEOS
from ..core.presentation_queue import STATE_LABELS


def presentation_item_text(item) -> str:
    suffix = "." + item.format.lower()
    if suffix in VIDEOS:
        count = tr("Видео")
    elif suffix in IMAGES:
        count = tr("Изображение")
    else:
        count = (
            tr("Слайдов: {p0}", p0=item.slide_count)
            if item.slide_count is not None
            else tr("Презентация")
        )
    return f"{item.name}\n{item.format} · {count}\n{tr(STATE_LABELS[item.state])}"
