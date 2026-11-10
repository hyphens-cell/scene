"""Read the visible pixels of our verified native slideshow, never another app."""

from __future__ import annotations

from PySide6.QtGui import QImage


def desktop_available() -> bool:
    """A locked/secure desktop cannot be captured by the presenter process."""
    import ctypes
    from ctypes import wintypes

    user = ctypes.windll.user32
    user.OpenInputDesktop.restype = wintypes.HANDLE
    handle = user.OpenInputDesktop(0, False, 1)
    if not handle:
        return False
    user.CloseDesktop(wintypes.HANDLE(handle))
    return True


def capture_show(hwnd: int) -> QImage:
    import win32con
    import win32gui
    import win32ui

    if (
        not desktop_available()
        or not hwnd
        or not win32gui.IsWindow(hwnd)
        or not win32gui.IsWindowVisible(hwnd)
    ):
        return QImage()
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    left, top = win32gui.ClientToScreen(hwnd, (left, top))
    right, bottom = win32gui.ClientToScreen(hwnd, (right, bottom))
    width, height = right - left, bottom - top
    if not 0 < width <= 8192 or not 0 < height <= 8192:
        return QImage()
    # A cover/modal/foreign foreground window invalidates screen capture.
    for x, y in (
        (left + 2, top + 2),
        (right - 3, bottom - 3),
        ((left + right) // 2, (top + bottom) // 2),
    ):
        if win32gui.GetAncestor(win32gui.WindowFromPoint((x, y)), 2) != hwnd:
            return QImage()
    handle = win32gui.GetDC(0)
    source = win32ui.CreateDCFromHandle(handle)
    destination = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    previous = None
    try:
        bitmap.CreateCompatibleBitmap(source, width, height)
        previous = destination.SelectObject(bitmap)
        destination.BitBlt(
            (0, 0),
            (width, height),
            source,
            (left, top),
            win32con.SRCCOPY | 0x40000000,  # CAPTUREBLT
        )
        info = bitmap.GetInfo()
        bits = bitmap.GetBitmapBits(True)
        # GetBitmapBits returns the screen DDB in top-to-bottom row order.
        # Detach from its Python buffer before releasing the GDI objects.
        return QImage(bits, width, height, info["bmWidthBytes"], QImage.Format.Format_RGB32).copy()
    finally:
        if previous is not None:
            destination.SelectObject(previous)
        win32gui.DeleteObject(bitmap.GetHandle())
        destination.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(0, handle)
