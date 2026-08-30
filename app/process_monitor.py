"""Process watching with psutil (spec §25, §26, §28, §29).

Only configured process names are examined; path check when readable.
"""
import os
import psutil


class ProcessMonitor:
    def __init__(self, log=None):
        self.log = log
        self._wanted = {}  # lower name -> list of (rule_index, full path)

    def set_rules(self, rules):
        wanted = {}
        for index, rule in enumerate(rules):
            name = rule.process_name.lower()
            wanted.setdefault(name, []).append((index, rule.path))
        self._wanted = wanted

    def wanted_names(self) -> set:
        return set(self._wanted)

    def tick(self):
        """Return {rule_index: pid}. Call every second from a QTimer (spec §26).

        Applications like chrome.exe run as a family of same-named processes;
        only the root process owns a window, helpers (renderer, GPU, utility)
        never do. The oldest root wins so the choice stays stable across ticks;
        helpers are only used as a last resort when no root exists.
        """
        if not self._wanted:
            return {}
        name_of = {}
        matches = []
        for proc in psutil.process_iter(["pid", "name", "ppid"]):
            try:
                name = (proc.info["name"] or "").lower()
                pid = proc.info["pid"]
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            name_of[pid] = name
            if name in self._wanted:
                matches.append((proc, pid, name, proc.info["ppid"]))
        roots = {}
        helpers = {}
        single_rule = len(self._wanted) <= 1
        for proc, pid, name, ppid in matches:
            picked = helpers if name_of.get(ppid) == name else roots
            exe = None
            if not single_rule:
                try:
                    exe = proc.exe()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    exe = None
            for index, configured_path in self._wanted[name]:
                if exe is None or _same_path(exe, configured_path):
                    if index not in picked or pid < picked[index]:
                        picked[index] = pid
        result = dict(roots)
        for index, pid in helpers.items():
            if index not in result:
                result[index] = pid
        return result

def is_same_path(exe: str, configured: str) -> bool:
    try:
        return os.path.normcase(os.path.abspath(exe)) == os.path.normcase(
            os.path.abspath(configured)
        )
    except (OSError, ValueError):
        return os.path.normcase(exe) == os.path.normcase(configured)


def same_path(exe: str, configured: str) -> bool:
    if not configured:
        return True
    return is_same_path(exe, configured)


def running_applications():
    """Unique readable exe paths with process names, sorted by name."""
    import psutil

    found = {}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            info = proc.info
            name = info.get("name") or ""
            exe = proc.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        if not exe:
            continue
        key = os.path.normcase(exe)
        if key not in found:
            found[key] = (name or exe.rsplit("\\")[-1], exe)
    return sorted(found.values(), key=lambda pair: pair[0].lower())


def _same_path(exe: str, configured: str) -> bool:
    if not configured:
        return True
    try:
        return os.path.normcase(os.path.abspath(exe)) == os.path.normcase(
            os.path.abspath(configured)
        )
    except (OSError, ValueError):
        return os.path.normcase(exe) == os.path.normcase(configured)
