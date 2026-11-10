from PySide6.QtCore import QRectF

MODES = {"fit", "fill", "stretch", "actual", "zoom"}


def media_rect(area: QRectF, source: tuple[float, float], settings: dict, dpr=1.0) -> QRectF:
    width, height = max(1, source[0]), max(1, source[1])
    mode = settings.get("scale", "fit")
    if mode == "stretch":
        return QRectF(area)
    if mode in {"actual", "zoom"}:
        ratio = (1 if mode == "actual" else settings.get("zoom", 100) / 100) / max(1, dpr)
    elif mode == "fill":
        ratio = max(area.width() / width, area.height() / height)
    else:
        ratio = min(area.width() / width, area.height() / height)
    width, height = width * ratio, height * ratio
    x = area.center().x() - width / 2 - settings.get("pan_x", 0) * max(0, width - area.width()) / 2
    y = (
        area.center().y()
        - height / 2
        - settings.get("pan_y", 0) * max(0, height - area.height()) / 2
    )
    return QRectF(x, y, width, height)
