"""Headless engine smoke test (run manually): notepad -> monitor 2, keep bound."""
import ctypes
import subprocess
import time

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ctypes.windll.shcore.SetProcessDpiAwareness(2)

from app.config import Rule, Settings, MonitorRef
from app.engine import RuleEngine, MONITOR_BOUND, PAUSED
from app.logger import setup_logging
from app import window_manager as wm

log = setup_logging(__import__("pathlib").Path("logs"), console=True)
monitors = None
import app.monitor_manager as mm

monitors = mm.list_monitors()
if len(monitors) < 2:
    raise SystemExit("need >=2 monitors, got %s" % monitors)
target = [m for m in monitors if m.index == 2][0]
other = [m for m in monitors if m.index != 2][0]
print("target:", target.label(), "other:", other.label())

ref = MonitorRef(target.index, target.device_name, target.resolution,
                  (target.left, target.top, target.right, target.bottom))
rule = Rule(path=r"C:\Windows\System32\notepad.exe", process_name="notepad.exe",
            monitor=ref, move_on_start=True, keep_on_monitor=True, maximize=False)
engine = RuleEngine([rule], Settings(), log)
engine.refresh_monitors()

proc = subprocess.Popen("notepad.exe")
deadline = time.monotonic() + 40
statuses = []
while time.monotonic() < deadline:
    engine.proc_tick()
    engine.fast_tick()
    engine.keep_tick()
    status = engine.runtimes[0].status
    if status not in statuses:
        statuses.append(status)
        print("status:", status)
    if status == MONITOR_BOUND:
        break
    time.sleep(0.25)
else:
    proc.terminate()
    raise SystemExit("FAILED to bind; statuses=%s" % statuses)

# Manual move to another monitor, then keep_tick must pull it back (spec §13/§52 Test5).
user32 = ctypes.windll.user32
hwnd = engine.runtimes[0].hwnd
user32.SetWindowPos(ctypes.c_void_p(hwnd), None, other.left + 50, other.top + 50,
                    0, 0, 0x0001 | 0x0004)
time.sleep(1.0)
print("after manual move:", wm.window_monitor_device_name(hwnd))
engine.keep_tick()
time.sleep(0.3)
back = wm.window_monitor_device_name(hwnd)
print("after keep_tick:", back)
assert back == target.device_name, "keep-on-monitor failed"
print("KEEP_OK")

# Pause test: while paused, no move back.
user32.SetWindowPos(ctypes.c_void_p(hwnd), None, other.left + 60, other.top + 50,
                    0, 0, 0x0001 | 0x0004)
engine.paused = True
engine.keep_tick()
still = wm.window_monitor_device_name(hwnd)
print("paused, still on:", still)
assert still == other.device_name, "pause did not hold"
print("PAUSE_OK")

engine.paused = False
engine.keep_tick()
assert wm.window_monitor_device_name(hwnd) == target.device_name
print("UNPAUSE_OK")
proc.terminate()
print("ALL_OK")
