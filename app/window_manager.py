"""Window discovery and movement via public Win32 window APIs (spec §10, §12, §14, §15).

No injection, no hooks — only documented window management APIs.
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

SW_MAXIMIZE = 3
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

_ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPVOID)
_enum_keepalive = []


class WINDOWRECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
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
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsZoomed.argtypes = [wintypes.HWND]
user32.IsZoomed.restype = wintypes.BOOL


def _window_rect(hwnd):
    rect = WINDOWRECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return rect


def window_title(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if not length:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
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
            hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value)
        )
        return hr == 0 and value.value != 0
    except Exception:
        return False


def _is_tool_window(hwnd) -> bool:
    exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    return bool(exstyle & WS_EX_TOOLWINDOW)


def _candidate_windows(pid: int) -> list:
    """Collect plausible main windows belonging to pid (spec §10)."""
    found = []

    def callback(hwnd, lparam):
        pid_out = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
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
        area = (rect.right - rect.left) * (rect.bottom - rect.top)
        if area <= 0:
            return True
        tool = _is_tool_window(hwnd)
        if tool and not (user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_APPWINDOW):
            return True
        found.append((int(hwnd or 0), title, area, bool(WS_EX_APPWINDOW & user32.GetWindowLongW(hwnd, GWL_EXSTYLE))))
        return True

    proc = _ENUM_WINDOWS_PROC(callback)
    _enum_keepalive.append(proc)
    user32.EnumWindows(proc, None)
    # EnumWindows returns topmost-first; reverse so app windows rank naturally.
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
    """Best-effort main window for a process; None if nothing plausible."""
    candidates = _candidate_windows(pid)
    if not candidates:
        return None
    best = None
    best_score = -1
    for hwnd, title, area, appwindow in candidates:
        score = _score(hwnd, title, area, appwindow, proc_name)
        if score > best_score:
            best_score = score
            best = hwnd
    return best


def is_valid(hwnd) -> bool:
    return bool(user32.IsWindow(wintypes.HWND(hwnd)))


def window_monitor_device_name(hwnd):
    info = monitor_from_window(hwnd)
    if info is None:
        return None
    return info.szDevice


def move_to_monitor_rect(hwnd, monitor):
    """Move window onto the monitor, keeping its current size (spec §12).

    Returns True when the window demonstrably ended up inside the monitor.

    A maximized window ignores position-only SetWindowPos calls (and Chrome
    additionally ignores SWP_NOSIZE moves), so the target geometry is always
    given explicitly and a maximized window is re-maximized on the target
    monitor (spec §35). The ±8 px tolerance covers the invisible resize
    borders a maximized window carries.
    """
    rect = _window_rect(hwnd)
    if rect is None:
        return False
    hwnd_arg = wintypes.HWND(hwnd)
    zoomed = bool(user32.IsZoomed(hwnd_arg))
    if zoomed:
        left, top = monitor.left, monitor.top
        width, height = monitor.width, monitor.height
    else:
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        # Center the window on the target monitor; works with negative coords (§38).
        left = monitor.left + (monitor.width - width) // 2
        top = monitor.top + (monitor.height - height) // 2
    user32.SetWindowPos(
        hwnd_arg,
        None,
        left,
        top,
        width,
        height,
        SWP_NOZORDER | SWP_NOACTIVATE,
    )
    if zoomed:
        user32.ShowWindow(hwnd_arg, SW_MAXIMIZE)
    verify = _window_rect(hwnd)
    if verify is None:
        return False
    inside = (
        verify.left >= monitor.left - 8
        and verify.top >= monitor.top - 8
        and verify.right <= monitor.right + 8
        and verify.bottom <= monitor.bottom + 8
    )
    return inside


def maximize(hwnd):
    user32.ShowWindow(wintypes.HWND(hwnd), SW_MAXIMIZE)
