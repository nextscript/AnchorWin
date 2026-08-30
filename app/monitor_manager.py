"""Monitor enumeration via Win32 display APIs (spec §8, §37, §38)."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)

MONITOR_DEFAULTTONEAREST = 2
MONITOR_DEFAULTTOPRIMARY = 1
MONITORINFOF_PRIMARY = 1


@dataclass
class MonitorInfo:
    index: int
    device_name: str
    left: int
    top: int
    right: int
    bottom: int
    width: int
    height: int
    is_primary: bool

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    def label(self) -> str:
        base = f"Monitor {self.index} - {self.resolution}"
        return base + " - Primary" if self.is_primary else base


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class MONITORINFOEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", ctypes.c_wchar * 32),
    ]


_ENUM_MONITORS_PROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, wintypes.LPVOID, wintypes.LPVOID
)
_enum_callback_keepalive = []


def _query_monitor_info(hmon):
    info = MONITORINFOEX()
    info.cbSize = ctypes.sizeof(MONITORINFOEX)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return None
    return info


def _collect_monitor_handles():
    collected = []

    def callback(hmon, hdc, rect_ptr, lparam):
        collected.append(hmon)
        return True

    proc = _ENUM_MONITORS_PROC(callback)
    user32.EnumDisplayMonitors(None, None, proc, None)
    return collected


def list_monitors() -> list:
    """Return all active monitors ordered with the primary first (spec §8).

    In a DPI-aware process, rcMonitor bounds are physical pixels, so the
    rect size is the monitor's current resolution.
    """
    infos = []
    primary = None
    for hmon in _collect_monitor_handles():
        info = _query_monitor_info(hmon)
        if info is None:
            continue
        rect = info.rcMonitor
        entry = MonitorInfo(
            index=0,
            device_name=info.szDevice,
            left=rect.left,
            top=rect.top,
            right=rect.right,
            bottom=rect.bottom,
            width=rect.right - rect.left,
            height=rect.bottom - rect.top,
            is_primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
        )
        if entry.is_primary:
            primary = entry
        else:
            infos.append(entry)
    ordered = ([primary] if primary else []) + sorted(infos, key=lambda m: (m.left, m.top))
    for i, monitor in enumerate(ordered, start=1):
        monitor.index = i
    return ordered


def monitor_from_window(hwnd, default_flag=MONITOR_DEFAULTTONEAREST):
    hmon = user32.MonitorFromWindow(hwnd, default_flag)
    if not hmon:
        return None
    return _query_monitor_info(hmon)


def monitor_at(index: int, monitors: list):
    for monitor in monitors:
        if monitor.index == index:
            return monitor
    return None
