"""Forward presentation shortcuts only while our native show owns input focus.

The hook runs on its own Windows message thread. It neither stores text nor
observes keys in other applications; COM and Qt actions stay on their own threads.
"""

from __future__ import annotations

import sys
import threading

from PySide6.QtCore import QObject, Signal

from pdf_presenter.i18n import tr


def command_for_key(key: int, *, control=False, shift=False, alt=False, meta=False) -> str:
    if alt or meta:
        return ""
    if control:
        return {
            0x4F: "open",
            0x53: "save_project" if shift else "save_notes",
            0x4E: "notes",
            0x21: "previous_file",
            0x22: "next_file",
            0x0D: "open_selected",
            0x4C: "queue",
        }.get(key, "")
    if key == 0x74:
        return "start_current" if shift else "start"
    if 0x30 <= key <= 0x39:
        return f"digit:{key - 0x30}"
    if 0x60 <= key <= 0x69:
        return f"digit:{key - 0x60}"
    return {
        0x27: "next",
        0x28: "next",
        0x20: "next",
        0x22: "next",
        0x25: "previous",
        0x26: "previous",
        0x21: "previous",
        0x24: "first",
        0x23: "last",
        0x1B: "escape",
        0x42: "black",
        0x57: "white",
        0x08: "backspace",
        0x0D: "submit",
    }.get(key, "")


class NativeInputRouter(QObject):
    command = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.hwnd = 0
        self._thread = None
        self._thread_id = 0
        self._closing = threading.Event()

    def set_target(self, hwnd: int) -> None:
        self.hwnd = hwnd
        if hwnd and sys.platform == "win32" and self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name="Native show keys")
            self._thread.start()

    def _run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user, kernel = ctypes.windll.user32, ctypes.windll.kernel32
        result_type = ctypes.c_ssize_t
        callback_type = ctypes.WINFUNCTYPE(
            result_type, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )
        user.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            callback_type,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        user.SetWindowsHookExW.restype = wintypes.HHOOK
        user.CallNextHookEx.argtypes = [
            wintypes.HHOOK,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user.CallNextHookEx.restype = result_type
        user.GetForegroundWindow.restype = wintypes.HWND
        user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        user.GetAncestor.restype = wintypes.HWND
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        suppressed = set()

        class KeyData(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("extra", ctypes.c_size_t),
            ]

        def callback(code, message, data):
            if code >= 0 and self.hwnd and not self._closing.is_set():
                foreground = user.GetForegroundWindow()
                if foreground and user.GetAncestor(foreground, 2) == self.hwnd:
                    key = ctypes.cast(data, ctypes.POINTER(KeyData)).contents.vkCode
                    if message in (0x101, 0x105):  # key up / system key up
                        if key in suppressed:
                            suppressed.discard(key)
                            return 1
                    elif message in (0x100, 0x104):

                        def pressed(value):
                            return bool(user.GetAsyncKeyState(value) & 0x8000)

                        command = command_for_key(
                            key,
                            control=pressed(0x11),
                            shift=pressed(0x10),
                            alt=pressed(0x12),
                            meta=pressed(0x5B) or pressed(0x5C),
                        )
                        if command:
                            suppressed.add(key)
                            self.command.emit(command)
                            return 1
            return user.CallNextHookEx(None, code, message, data)

        procedure = callback_type(callback)
        hook = None
        try:
            self._thread_id = kernel.GetCurrentThreadId()
            hook = user.SetWindowsHookExW(13, procedure, kernel.GetModuleHandleW(None), 0)
            if not hook:
                self.failed.emit(
                    tr(
                        "Горячие клавиши доступны из окна докладчика; Windows не включила управление из окна PowerPoint."
                    )
                )
                return
            message = wintypes.MSG()
            while (
                not self._closing.is_set()
                and user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0
            ):
                user.TranslateMessage(ctypes.byref(message))
                user.DispatchMessageW(ctypes.byref(message))
        finally:
            if hook:
                user.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
                user.UnhookWindowsHookEx(hook)
            self._thread_id = 0

    def close(self) -> None:
        self.hwnd = 0
        self._closing.set()
        if self._thread_id:
            import ctypes

            ctypes.windll.user32.PostThreadMessageW(self._thread_id, 0x12, 0, 0)
        if self._thread:
            self._thread.join(timeout=0.5)
