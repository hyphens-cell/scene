"""Small, consistent vector icons for the native Qt interface."""

from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "repeat": '<path d="M4 10V7h13l-3-3m3 3-3 3M20 14v3H7l3 3m-3-3 3-3"/>',
    "link": '<path d="m9 15 6-6M8 12l-2 2a3 3 0 0 0 4 4l2-2m4-4 2-2a3 3 0 0 0-4-4l-2 2"/>',
    "play": '<path d="m8 5 11 7-11 7Z"/>',
    "pause": '<path d="M8 5v14M16 5v14"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "folder": '<path d="M3 7V5h6l2 3h10v11H3Z"/>',
    "screen": '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/>',
    "swap": '<path d="M4 8h16m-4-4 4 4-4 4M20 16H4m4-4-4 4 4 4"/>',
    "eye": '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    "up": '<path d="m6 14 6-6 6 6"/>',
    "down": '<path d="m6 10 6 6 6-6"/>',
    "left": '<path d="m14 6-6 6 6 6"/>',
    "right": '<path d="m10 6 6 6-6 6"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "volume": '<path d="M4 9h4l5-4v14l-5-4H4Zm13-1a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1"/><path d="m3 17 6-6 4 4 3-3 5 5"/>',
    "slides": '<rect x="3" y="3" width="18" height="14" rx="2"/><path d="m8 22 4-5 4 5M7 8h10M7 12h6"/>',
    "document": '<path d="M6 3h8l4 4v14H6Zm8 0v5h4M9 12h6m-6 4h6"/>',
    "lock": '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
}


@lru_cache(maxsize=128)
def icon(name: str, color: str = "#C3CCE0") -> QIcon:
    result = QIcon()
    for mode, stroke in ((QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, "#59657D")):
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            f'fill="none" stroke="{stroke}" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>'
        )
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        for size in (16, 20, 24, 32):
            pixmap = QPixmap(size * 2, size * 2)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            pixmap.setDevicePixelRatio(2)
            result.addPixmap(pixmap, mode)
    return result
