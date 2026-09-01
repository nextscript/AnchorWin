"""Window discovery and movement via public Win32 window APIs.

No injection, no hooks — only documented window management APIs.

Movement strategy:
- Normal windows: SetWindowPos.
- Maximized windows:
  1. Direct SetWindowPos while still maximized (no restore animation).
  2. WINDOWPLACEMENT relocation.
  3. Hidden fallback so Restore -> Move -> Maximize is not visibly drawn.
"""

import ctypes
from ctypes import wintypes

from app.monitor_manager import monitor_from_window


user32 = ctypes.WinDLL("user32", use_last_error=True)


def _load_dwm():
    try:
        return ctypes.WinDLL("dwmapi")
    except OSError:
        return None


_DWM = _load_dwm()

DWMWA_CLOAKED = 14

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMAXIMIZED = 3
SW_MAXIMIZE = 3
SW_RESTORE = 9

SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_ASYNCWINDOWPOS = 0x4000

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

_ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HWND,
    wintypes.LPVOID,
)

_enum_keepalive = []


class WINDOWRECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
    ]


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", POINT),
        ("ptMaxPosition", POINT),
        ("rcNormalPosition", WINDOWRECT),
    ]


user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(wintypes.DWORD),
]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

user32.GetWindowTextW.argtypes = [
    wintypes.HWND,
    wintypes.LPWSTR,
    ctypes.c_int,
]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetWindowLongW.argtypes = [
    wintypes.HWND,
    ctypes.c_int,
]
user32.GetWindowLongW.restype = ctypes.c_long

user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.IsZoomed.argtypes = [wintypes.HWND]
user32.IsZoomed.restype = wintypes.BOOL

user32.GetWindowRect.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(WINDOWRECT),
]
user32.GetWindowRect.restype = wintypes.BOOL

user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL

user32.ShowWindow.argtypes = [
    wintypes.HWND,
    ctypes.c_int,
]
user32.ShowWindow.restype = wintypes.BOOL

user32.GetWindowPlacement.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(WINDOWPLACEMENT),
]
user32.GetWindowPlacement.restype = wintypes.BOOL

user32.SetWindowPlacement.argtypes = [
    wintypes.HWND,
    ctypes.POINTER(WINDOWPLACEMENT),
]
user32.SetWindowPlacement.restype = wintypes.BOOL


def _window_rect(hwnd):
    rect = WINDOWRECT()

    if not user32.GetWindowRect(
        wintypes.HWND(hwnd),
        ctypes.byref(rect),
    ):
        return None

    return rect


def _get_window_placement(hwnd):
    placement = WINDOWPLACEMENT()
    placement.length = ctypes.sizeof(WINDOWPLACEMENT)

    if not user32.GetWindowPlacement(
        wintypes.HWND(hwnd),
        ctypes.byref(placement),
    ):
        return None

    return placement


def window_title(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)

    if not length:
        return ""

    buf = ctypes.create_unicode_buffer(length + 1)

    user32.GetWindowTextW(
        hwnd,
        buf,
        length + 1,
    )

    return buf.value


def _is_cloaked(hwnd) -> bool:
    if _DWM is None:
        return False

    try:
        _DWM.DwmGetWindowAttribute.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_int,
        ]

        value = ctypes.c_int(0)

        hr = _DWM.DwmGetWindowAttribute(
            hwnd,
            DWMWA_CLOAKED,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )

        return hr == 0 and value.value != 0

    except Exception:
        return False


def _is_tool_window(hwnd) -> bool:
    exstyle = user32.GetWindowLongW(
        hwnd,
        GWL_EXSTYLE,
    )

    return bool(exstyle & WS_EX_TOOLWINDOW)


def _candidate_windows(pid: int) -> list:
    found = []

    def callback(hwnd, lparam):
        pid_out = wintypes.DWORD(0)

        user32.GetWindowThreadProcessId(
            hwnd,
            ctypes.byref(pid_out),
        )

        if pid_out.value != pid:
            return True

        if not user32.IsWindowVisible(hwnd):
            return True

        if _is_cloaked(hwnd):
            return True

        title = window_title(hwnd)
        rect = _window_rect(hwnd)

        if not title or rect is None:
            return True

        width = rect.right - rect.left
        height = rect.bottom - rect.top
        area = width * height

        if area <= 0:
            return True

        exstyle = user32.GetWindowLongW(
            hwnd,
            GWL_EXSTYLE,
        )

        tool = bool(exstyle & WS_EX_TOOLWINDOW)
        appwindow = bool(exstyle & WS_EX_APPWINDOW)

        if tool and not appwindow:
            return True

        found.append(
            (
                int(hwnd or 0),
                title,
                area,
                appwindow,
            )
        )

        return True

    proc = _ENUM_WINDOWS_PROC(callback)
    _enum_keepalive.append(proc)

    user32.EnumWindows(
        proc,
        None,
    )

    found.reverse()

    return found


def _score(hwnd, title, area, appwindow, proc_name: str):
    name = proc_name.lower()
    stem = name[:-4] if name.endswith(".exe") else name
    lowered = title.lower()

    score = 0

    if appwindow:
        score += 1000

    if stem and stem in lowered:
        score += 500

    score += min(area // 1000, 400)

    return score


def find_main_window(pid: int, proc_name: str = ""):
    candidates = _candidate_windows(pid)

    if not candidates:
        return None

    best = None
    best_score = -1

    for hwnd, title, area, appwindow in candidates:
        score = _score(
            hwnd,
            title,
            area,
            appwindow,
            proc_name,
        )

        if score > best_score:
            best_score = score
            best = hwnd

    return best


def is_valid(hwnd) -> bool:
    return bool(
        user32.IsWindow(
            wintypes.HWND(hwnd)
        )
    )


def window_monitor_device_name(hwnd):
    info = monitor_from_window(hwnd)

    if info is None:
        return None

    return info.szDevice


def is_maximized(hwnd) -> bool:
    return bool(
        user32.IsZoomed(
            wintypes.HWND(hwnd)
        )
    )


def _center_position(monitor, width: int, height: int):
    left = monitor.left + (monitor.width - width) // 2
    top = monitor.top + (monitor.height - height) // 2

    left = max(monitor.left, left)
    top = max(monitor.top, top)

    return left, top


def _move_normal_window(hwnd, monitor) -> bool:
    rect = _window_rect(hwnd)

    if rect is None:
        return False

    width = rect.right - rect.left
    height = rect.bottom - rect.top

    if width <= 0 or height <= 0:
        return False

    left, top = _center_position(
        monitor,
        width,
        height,
    )

    return bool(
        user32.SetWindowPos(
            wintypes.HWND(hwnd),
            None,
            left,
            top,
            0,
            0,
            SWP_NOSIZE
            | SWP_NOZORDER
            | SWP_NOACTIVATE
            | SWP_ASYNCWINDOWPOS,
        )
    )


def _move_maximized_direct(hwnd, monitor) -> bool:
    """First choice: move the HWND while it remains maximized.

    No SW_RESTORE is used, so Windows has no restored-size transition
    to animate on screen.
    """

    hwnd_arg = wintypes.HWND(hwnd)
    rect = _window_rect(hwnd)

    if rect is None:
        return False

    current_info = monitor_from_window(hwnd)

    if current_info is None:
        return False

    # Preserve the maximized frame's offset relative to its current monitor.
    # This is important because maximized DWM frames can extend a few pixels
    # outside the nominal monitor rectangle.
    offset_x = rect.left - current_info.rcMonitor.left
    offset_y = rect.top - current_info.rcMonitor.top

    target_x = monitor.left + offset_x
    target_y = monitor.top + offset_y

    if not user32.SetWindowPos(
        hwnd_arg,
        None,
        target_x,
        target_y,
        0,
        0,
        SWP_NOSIZE
        | SWP_NOZORDER
        | SWP_NOACTIVATE
        | SWP_ASYNCWINDOWPOS,
    ):
        return False

    # Keep the maximized show state. This is normally already true, but the
    # explicit call helps applications that partially update their state.
    if not user32.IsZoomed(hwnd_arg):
        user32.ShowWindow(hwnd_arg, SW_MAXIMIZE)

    return window_monitor_device_name(hwnd) == monitor.device_name


def _move_maximized_placement(hwnd, monitor) -> bool:
    """Second choice: change the restored rectangle without restoring."""

    placement = _get_window_placement(hwnd)

    if placement is None:
        return False

    normal = placement.rcNormalPosition

    width = normal.right - normal.left
    height = normal.bottom - normal.top

    if width <= 0 or height <= 0:
        return False

    left, top = _center_position(
        monitor,
        width,
        height,
    )

    placement.rcNormalPosition.left = left
    placement.rcNormalPosition.top = top
    placement.rcNormalPosition.right = left + width
    placement.rcNormalPosition.bottom = top + height
    placement.showCmd = SW_SHOWMAXIMIZED

    if not user32.SetWindowPlacement(
        wintypes.HWND(hwnd),
        ctypes.byref(placement),
    ):
        return False

    return (
        window_monitor_device_name(hwnd)
        == monitor.device_name
    )


def _move_maximized_hidden_fallback(hwnd, monitor) -> bool:
    """Compatibility fallback.

    Some applications refuse to move while maximized. In that case the old
    Restore -> Move -> Maximize sequence is still required, but the window is
    hidden before changing state so the user does not see it shrink first.
    """

    hwnd_arg = wintypes.HWND(hwnd)

    if not user32.IsWindow(hwnd_arg):
        return False

    # Hide first so the restore geometry is not visibly animated.
    user32.ShowWindow(hwnd_arg, SW_HIDE)

    user32.ShowWindow(hwnd_arg, SW_RESTORE)

    if not user32.IsWindow(hwnd_arg):
        return False

    rect = _window_rect(hwnd)

    if rect is None:
        user32.ShowWindow(hwnd_arg, SW_MAXIMIZE)
        return False

    width = rect.right - rect.left
    height = rect.bottom - rect.top

    if width <= 0 or height <= 0:
        user32.ShowWindow(hwnd_arg, SW_MAXIMIZE)
        return False

    left, top = _center_position(
        monitor,
        width,
        height,
    )

    moved = user32.SetWindowPos(
        hwnd_arg,
        None,
        left,
        top,
        width,
        height,
        SWP_NOZORDER
        | SWP_NOACTIVATE
        | SWP_ASYNCWINDOWPOS,
    )

    # Show it again only in the final maximized state.
    user32.ShowWindow(
        hwnd_arg,
        SW_MAXIMIZE,
    )

    return bool(moved)


def move_to_monitor_rect(hwnd, monitor):
    """Move the window to the requested monitor.

    Maximized windows are handled without a visible restore transition whenever
    possible. The engine performs a delayed verification afterwards.
    """

    hwnd_arg = wintypes.HWND(hwnd)

    if not user32.IsWindow(hwnd_arg):
        return False

    if (
        window_monitor_device_name(hwnd)
        == monitor.device_name
    ):
        return True

    maximized = bool(
        user32.IsZoomed(hwnd_arg)
    )

    if not maximized:
        return _move_normal_window(
            hwnd,
            monitor,
        )

    # 1. Best path: move maximized HWND directly.
    if _move_maximized_direct(
        hwnd,
        monitor,
    ):
        return True

    # 2. Try WINDOWPLACEMENT without exposing a restored state.
    if _move_maximized_placement(
        hwnd,
        monitor,
    ):
        return True

    # 3. Last resort: compatibility sequence, but hidden while restored.
    return _move_maximized_hidden_fallback(
        hwnd,
        monitor,
    )


def maximize(hwnd):
    hwnd_arg = wintypes.HWND(hwnd)

    if not user32.IsWindow(hwnd_arg):
        return False

    if user32.IsZoomed(hwnd_arg):
        return True

    user32.ShowWindow(
        hwnd_arg,
        SW_MAXIMIZE,
    )

    return True
