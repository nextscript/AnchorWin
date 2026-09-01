"""Config storage for AnchorWin (spec §17–19, §42: auto-save, backup, portable mode)."""
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "AnchorWin"
APP_TITLE = "AnchorWin v1.0.2"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def exe_dir() -> Path:
    if is_frozen():
        return Path(sys.executable).parent
    return Path(os.path.abspath(os.path.dirname(__file__))).parent


def appdata_dir() -> Path:
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_NAME


@dataclass
class MonitorRef:
    """Stored monitor identity (spec §9). device_name is the stable key."""
    monitor_index: int = 0
    device_name: str = ""
    resolution: str = ""
    position: tuple = (0, 0, 0, 0)  # left, top, right, bottom

    def to_json(self):
        return {
            "monitor_index": self.monitor_index,
            "device_name": self.device_name,
            "resolution": self.resolution,
            "position": list(self.position),
        }

    @staticmethod
    def from_json(data: dict):
        return MonitorRef(
            monitor_index=int(data.get("monitor_index", 0)),
            device_name=str(data.get("device_name", "")),
            resolution=str(data.get("resolution", "")),
            position=tuple(data.get("position", (0, 0, 0, 0))),
        )


@dataclass
class Rule:
    path: str
    process_name: str
    monitor: MonitorRef
    move_on_start: bool = True
    keep_on_monitor: bool = True
    maximize: bool = False

    def to_json(self):
        return {
            "path": self.path,
            "process_name": self.process_name,
            "monitor": self.monitor.to_json(),
            "move_on_start": self.move_on_start,
            "keep_on_monitor": self.keep_on_monitor,
            "maximize": self.maximize,
        }

    @staticmethod
    def from_json(data: dict):
        return Rule(
            path=str(data.get("path", "")),
            process_name=str(data.get("process_name", "")),
            monitor=MonitorRef.from_json(data.get("monitor", {})),
            move_on_start=bool(data.get("move_on_start", True)),
            keep_on_monitor=bool(data.get("keep_on_monitor", True)),
            maximize=bool(data.get("maximize", False)),
        )


@dataclass
class Settings:
    autostart: bool = False
    keep_all_on_monitor: bool = True
    start_minimized: bool = False

    def to_json(self):
        return {
            "autostart": self.autostart,
            "keep_all_on_monitor": self.keep_all_on_monitor,
            "start_minimized": self.start_minimized,
        }

    @staticmethod
    def from_json(data: dict):
        return Settings(
            autostart=bool(data.get("autostart", False)),
            keep_all_on_monitor=bool(data.get("keep_all_on_monitor", True)),
            start_minimized=bool(data.get("start_minimized", False)),
        )


@dataclass
class ConfigData:
    rules: list = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)


class Config:
    """Loads/saves %APPDATA%\\AnchorWin\\config.json; keeps config.json.bak."""

    def __init__(self, log=None):
        self.log = log
        self.dir = self._resolve_dir()
        self.path = self.dir / "config.json"
        self.backup_path = self.dir / "config.json.bak"
        self.data = ConfigData()
        self.corrupt_fallback = False
        self.load()

    def _resolve_dir(self) -> Path:
        data_dir = exe_dir() / "portable.flag"
        if data_dir.exists():
            return exe_dir()
        return appdata_dir()

    def load(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        for candidate in (self.path, self.backup_path):
            if not candidate.exists():
                continue
            try:
                raw = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                if candidate == self.path:
                    self._log("warn", f"config.json unreadable ({exc}); trying backup")
                self.corrupt_fallback = candidate == self.backup_path
                continue
            self.data = ConfigData(
                rules=[Rule.from_json(r) for r in raw.get("applications", [])],
                settings=Settings.from_json(raw.get("settings", {})),
            )
            return
        self.data = ConfigData()

    def save(self):
        raw = {
            "applications": [r.to_json() for r in self.data.rules],
            "settings": self.data.settings.to_json(),
        }
        text = json.dumps(raw, indent=2, ensure_ascii=False)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        if self.path.exists():
            try:
                self.path.replace(self.backup_path)
            except OSError:
                self.backup_path.write_bytes(self.path.read_bytes())
        tmp.replace(self.path)

    def add_rule(self, rule: Rule):
        self.data.rules.append(rule)
        self.save()

    def update_rule(self, index: int, rule: Rule):
        self.data.rules[index] = rule
        self.save()

    def delete_rule(self, index: int):
        del self.data.rules[index]
        self.save()

    def save_settings(self):
        self.save()

    def _log(self, level, message):
        if self.log:
            getattr(self.log, level)(message)
