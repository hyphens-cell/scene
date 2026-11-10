"""Native slideshow positioning; only handles returned by our Office sessions."""

from __future__ import annotations

from pdf_presenter.i18n import tr

from ..core.capability_model import DisplayTarget


def visible_powerpoint_windows() -> set[int]:
    import win32gui
    import win32process

    pids = running_office_pids("POWERPNT.EXE")
    windows = set()

    def visit(hwnd, _):
        if (
            win32gui.IsWindowVisible(hwnd)
            and win32process.GetWindowThreadProcessId(hwnd)[1] in pids
        ):
            windows.add(hwnd)

    win32gui.EnumWindows(visit, None)
    return windows


def find_created_show(previous: set[int], source_stem: str = "") -> int:
    import time

    import pythoncom
    import win32gui

    # Some Office builds expose HWND only through their vtable, not IDispatch.
    # Accept only a newly visible slideshow/frame belonging to POWERPNT.EXE.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        pythoncom.PumpWaitingMessages()
        candidates = [
            hwnd
            for hwnd in visible_powerpoint_windows() - previous
            if win32gui.GetClassName(hwnd) in {"screenClass", "PPTFrameClass"}
        ]
        if len(candidates) == 1:
            return candidates[0]
        # Windowed PowerPoint may reuse its already visible application frame.
        # Its slideshow caption encloses the document name in square brackets;
        # an ordinary editor window does not. The caller has already excluded
        # presentations opened independently by the user.
        named = [
            hwnd
            for hwnd in visible_powerpoint_windows()
            if win32gui.GetClassName(hwnd) == "PPTFrameClass"
            and source_stem
            and f"[{source_stem.casefold()}" in win32gui.GetWindowText(hwnd).casefold()
        ]
        if len(named) == 1:
            return named[0]
        time.sleep(0.02)
    raise RuntimeError(
        tr(
            "Не удалось однозначно определить созданное окно показа. Чужие окна PowerPoint не перемещались."
        )
    )


def running_office_pids(executable: str) -> set[int]:
    import win32api
    import win32process

    result = set()
    for pid in win32process.EnumProcesses():
        handle = None
        try:
            handle = win32api.OpenProcess(0x1000, False, pid)
            name = win32process.GetModuleFileNameEx(handle, 0)
            if name.replace("\\", "/").rsplit("/", 1)[-1].casefold() == executable.casefold():
                result.add(pid)
        except Exception:
            pass
        finally:
            if handle is not None:
                handle.Close()
    return result


def window_handle(window) -> int:
    import pythoncom

    # Some PowerPoint type libraries describe HWND as a method even though the
    # automation implementation accepts PROPERTYGET. Invoke it explicitly.
    dispatch_id = window._oleobj_.GetIDsOfNames("HWND")
    return int(window._oleobj_.Invoke(dispatch_id, 0, pythoncom.DISPATCH_PROPERTYGET, True))


def position_window(hwnd: int, target: DisplayTarget) -> tuple[int, int, int, int]:
    import win32api
    import win32con
    import win32gui

    if not win32gui.IsWindow(hwnd):
        raise RuntimeError(tr("Окно показа больше не существует."))
    geometry = None
    monitors = [
        win32api.GetMonitorInfo(monitor) for monitor, _, _ in win32api.EnumDisplayMonitors()
    ]
    for info in monitors:
        if info["Device"] == (target.native_device or target.name):
            geometry = info["Work"] if target.preview else info["Monitor"]
            break
    if geometry is None and not target.native_device:
        # Qt may report an EDID model name (e.g. V-215) instead of DISPLAY5.
        # On Windows Qt keeps native virtual-desktop origins even at mixed DPI.
        # GUI handoffs pass an explicit device obtained from their cover HWND;
        # this unique-origin fallback also supports standalone engine callers.
        matches = [info for info in monitors if info["Monitor"][:2] == (target.x, target.y)]
        if len(matches) == 1:
            geometry = matches[0]["Work"] if target.preview else matches[0]["Monitor"]
    if geometry is None:
        raise RuntimeError(
            tr("Выбранный экран отключён. Показ остановлен для защиты экрана докладчика.")
        )
    x, y, right, bottom = geometry
    width, height = right - x, bottom - y
    if target.preview:
        width, height = min(800, width * 2 // 3), min(500, height * 2 // 3)
        x, y = right - width - 24, bottom - height - 24
    else:
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style &= ~(
            win32con.WS_CAPTION
            | win32con.WS_THICKFRAME
            | win32con.WS_MINIMIZEBOX
            | win32con.WS_MAXIMIZEBOX
        )
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
    # The Qt handoff cover stays topmost until the window is placed and verified.
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_NOTOPMOST,
        x,
        y,
        width,
        height,
        win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW,
    )
    actual = win32gui.GetWindowRect(hwnd)
    if not target.preview and any(
        abs(a - b) > 4 for a, b in zip(actual, (x, y, x + width, y + height), strict=True)
    ):
        win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
        raise RuntimeError(tr("Не удалось безопасно разместить окно показа на выбранном экране."))
    return actual
