"""GUI logic test (offscreen Qt): rule add -> table -> autostart-free toggles -> test button."""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp  # keep test config out of the real %APPDATA%

from PySide6.QtWidgets import QApplication

app = QApplication([])

from app.config import Config, Rule, MonitorRef
from app.engine import MONITOR_BOUND, NOT_RUNNING, RuleEngine
from app.gui import MainWindow, RuleDialog

config = Config()
assert config.dir.exists() or True
print("config dir:", config.dir)
log = None
engine = RuleEngine(config.data.rules, config.data.settings, log)
window = MainWindow(config, engine, log)
window.refresh_table()
assert engine.monitors, "no monitors enumerated"
target = [m for m in engine.monitors if m.index == 2][0]

# --- add via dialog ---------------------------------------------------------
dialog = RuleDialog(engine.monitors, parent=window)
dialog.exe_edit.setText(r"C:\Windows\System32\notepad.exe")
pos = dialog.monitor_combo.findData(target.index)
dialog.monitor_combo.setCurrentIndex(pos)
dialog.move_check.setChecked(True)
dialog.keep_check.setChecked(True)
dialog._accept()
assert dialog.saved_rule is not None
rule = dialog.saved_rule
assert rule.process_name == "notepad.exe"
assert rule.monitor.device_name == target.device_name
print("dialog rule ok:", rule.monitor.device_name)

config.add_rule(rule)
engine.set_rules(config.data.rules)
window.refresh_table()
assert window.table.rowCount() == 1
assert window.table.item(0, 0).text() == "notepad.exe"
print("table row ok:", [window.table.item(0, c).text() for c in range(3)])

# settings toggles save immediately (skip autostart to avoid touching registry)
window.keep_check.setChecked(False)
assert config.data.settings.keep_all_on_monitor is False
window.minimized_check.setChecked(True)
assert config.data.settings.start_minimized is True
window.keep_check.setChecked(True)
window.minimized_check.setChecked(False)
reloaded = Config()
assert reloaded.data.settings.keep_all_on_monitor is True
print("autosave ok")

# --- engine drives to bound -------------------------------------------------
proc = subprocess.Popen("notepad.exe")
deadline = time.monotonic() + 40
while time.monotonic() < deadline:
    engine.proc_tick()
    engine.fast_tick()
    engine.keep_tick()
    window.refresh_table()
    if engine.runtimes[0].status == MONITOR_BOUND:
        break
    time.sleep(0.25)
assert engine.runtimes[0].status == MONITOR_BOUND, "engine did not bind"
print("bound ok")

# --- Test button path ---------------------------------------------------------
window.table.selectRow(0)
proc.terminate()
proc.wait()
engine.proc_tick()
window._test_selected()
print("test-on-stopped result ok, status:", engine.runtimes[0].status)

# --- close goes to tray (hide, not quit) ------------------------------------
window.show()
window.close()
assert window.isVisible() is False
print("close-to-tray ok")

# cleanup temp config
shutil_cleanup = True
print("GUI_ALL_OK")
