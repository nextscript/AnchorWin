"""Autostart via HKCU Run key, no admin rights needed (spec §20)."""
import os
import sys
import winreg

from app.config import APP_NAME, is_frozen


def _command() -> str:
    if is_frozen():
        return f'"{sys.executable}"'
    pythonw = _pythonw()
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
    return f'"{pythonw}" "{script}"'


def _pythonw() -> str:
    base = os.path.dirname(sys.executable)
    candidate = os.path.join(base, "pythonw.exe")
    if os.path.exists(candidate):
        return candidate
    return sys.executable


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except OSError:
                    pass
        return True
    except OSError:
        return False
