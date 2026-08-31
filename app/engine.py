"""Rule engine: watch processes, find windows, move windows, keep them bound.

Pure state machine driven from QTimers (spec §25: no busy loops). The class
contains no Qt code so it is testable headless; timers call proc_tick(),
fast_tick() and keep_tick().
"""
import os
import time

from app.monitor_manager import list_monitors
from app.process_monitor import ProcessMonitor
from app.window_manager import (
    find_main_window,
    is_maximized,
    is_valid,
    maximize,
    move_to_monitor_rect,
    window_monitor_device_name,
)

NOT_RUNNING = "Not Running"
RUNNING = "Running"
WINDOW_FOUND = "Window Found"
WINDOW_MISSING = "Window Missing"
MONITOR_BOUND = "Monitor Bound"
PAUSED = "Rules paused"
UNMOVABLE = "Fullscreen window could not be moved"
MONITOR_UNAVAILABLE = "Assigned monitor unavailable"

WINDOW_SEARCH_TIMEOUT = 30.0  # spec §11: search max 30 s after process start
VERIFY_DELAY = 0.5  # spec §35: verify 500 ms after moving
MAX_MOVE_ATTEMPTS = 5  # spec §35, §36

PHASE_IDLE = "idle"
PHASE_SEARCH = "search"
PHASE_MOVING = "moving"
PHASE_VERIFY = "verify"
PHASE_BOUND = "bound"
PHASE_GIVEN_UP = "given_up"


def _rule_path_key(path):
    """Normalized identity for a rule's executable path (spec §36)."""
    try:
        return os.path.normcase(os.path.abspath(path))
    except (OSError, ValueError):
        return os.path.normcase(path)

class RuleRuntime:
    __slots__ = (
        "rule",
        "pid",
        "hwnd",
        "phase",
        "deadline",
        "verify_at",
        "attempts",
        "status",
    )

    def __init__(self, rule):
        self.rule = rule
        self.pid = None
        self.hwnd = None
        self.phase = PHASE_IDLE
        self.deadline = 0.0
        self.verify_at = 0.0
        self.attempts = 0
        self.status = NOT_RUNNING


class RuleEngine:
    def __init__(self, rules, settings, log=None):
        self.log = log
        self.settings = settings
        self.processes = ProcessMonitor(log)
        self.monitors = list_monitors()
        self.runtimes = [RuleRuntime(rule) for rule in rules]
        self.processes.set_rules(rules)
        self.paused = False
        self.on_update = None

    # ---- configuration ---------------------------------------------------

    def set_rules(self, rules):
        """Rebuild runtimes from updated config, migrating live state (spec §34-48).

        Harmless edits preserve the whole runtime; a changed target monitor
        starts a new move cycle; dead HWNDs are re-discovered.
        """
        old_by_path = {}
        for rt in self.runtimes:
            old_by_path[_rule_path_key(rt.rule.path)] = rt
        self.runtimes = []
        now = time.monotonic()
        for rule in rules:
            rt = RuleRuntime(rule)
            previous = old_by_path.get(_rule_path_key(rule.path))
            if previous is not None:
                self._migrate_runtime(rt, previous, rule, now)
            self.runtimes.append(rt)
        self.processes.set_rules(rules)

    def _migrate_runtime(self, rt, previous, rule, now):
        """Carry live state across a rule refresh, then normalize (spec §46, §47)."""
        rt.pid = previous.pid
        rt.hwnd = previous.hwnd
        rt.phase = previous.phase
        rt.deadline = previous.deadline
        rt.verify_at = previous.verify_at
        rt.attempts = previous.attempts
        rt.status = previous.status

        if rt.pid is None:
            rt.hwnd = None
            rt.phase = PHASE_IDLE
            rt.status = NOT_RUNNING
            return

        monitor_changed = (
            previous.rule.monitor.device_name != rule.monitor.device_name
            or previous.rule.monitor.monitor_index != rule.monitor.monitor_index
        )
        if monitor_changed:
            # New target: start a fresh move cycle (spec §41, §43).
            rt.attempts = 0
            rt.verify_at = 0.0

        if rt.hwnd is not None and not is_valid(rt.hwnd):
            self._lose_window(rt, now)
            return

        if monitor_changed and rule.move_on_start and rt.hwnd is not None:
            rt.phase = PHASE_MOVING
            rt.status = WINDOW_FOUND
        elif rt.hwnd is None:
            self._lose_window(rt, now)
        elif not rule.move_on_start and rt.phase in (PHASE_MOVING, PHASE_VERIFY):
            # Obsolete move sequence; cancel it (spec §42).
            rt.phase = PHASE_IDLE
            rt.status = WINDOW_FOUND

    def refresh_monitors(self):
        self.monitors = list_monitors()

    def _resolve_monitor(self, rt):
        """Find the configured monitor in the current enumeration (spec §9, §41)."""
        stored = rt.rule.monitor
        wanted = None
        for monitor in self.monitors:
            if monitor.device_name == stored.device_name:
                wanted = monitor
                break
        if wanted is not None:
            return wanted
        # Fall back to the stored index when devices were renumbered or renamed
        # (driver update / cable swap case, spec §9).
        fallback = None
        for monitor in self.monitors:
            if monitor.index == stored.monitor_index:
                fallback = monitor
                break
        if fallback is None:
            return None
        stored.device_name = fallback.device_name
        return fallback

    # ---- timers ------------------------------------------------------------

    def proc_tick(self):
        """1 Hz process scan (spec §26)."""
        running = self.processes.tick()
        now = time.monotonic()
        for i, rt in enumerate(self.runtimes):
            pid = running.get(i)
            if pid is None:
                if rt.pid is not None:
                    self._loginfo(f"Process gone {rt.rule.process_name} PID {rt.pid}")
                    self._reset(rt, NOT_RUNNING)
                continue
            if rt.pid != pid:
                rt.pid = pid
                # Fresh launch: previous window/retry state is obsolete (§43).
                rt.hwnd = None
                rt.attempts = 0
                rt.verify_at = 0.0
                self._loginfo(f"Detected {rt.rule.process_name} PID {pid}")
                rt.phase = PHASE_SEARCH
                rt.deadline = now + WINDOW_SEARCH_TIMEOUT
                rt.status = RUNNING

    def fast_tick(self):
        """250 ms window search/move loop; only runs while phases are active (§11)."""
        now = time.monotonic()
        for rt in self.runtimes:
            if rt.phase in (PHASE_SEARCH, PHASE_MOVING, PHASE_VERIFY):
                self._fast_step(rt, now)

    def needs_fast_ticker(self) -> bool:
        return any(
            rt.phase in (PHASE_SEARCH, PHASE_MOVING, PHASE_VERIFY)
            for rt in self.runtimes
        )

    def needs_keep_ticker(self) -> bool:
        if self.paused or not self.settings.keep_all_on_monitor:
            return False
        return any(
            rt.phase == PHASE_BOUND and rt.rule.keep_on_monitor
            for rt in self.runtimes
        )

    def keep_tick(self):
        """500–1000 ms keep-on-monitor check (spec §13): move only when drifted."""
        now = time.monotonic()
        for rt in self.runtimes:
            if rt.phase != PHASE_BOUND or not rt.rule.keep_on_monitor:
                continue
            if self.paused or not self.settings.keep_all_on_monitor:
                rt.status = PAUSED if self.paused else MONITOR_BOUND
                continue
            if rt.hwnd is None or not is_valid(rt.hwnd):
                # Process still runs but its window was recreated: rediscover.
                self._lose_window(rt, now)
                continue
            device = window_monitor_device_name(rt.hwnd)
            configured = self._resolve_monitor(rt)
            if configured is None:
                rt.status = MONITOR_UNAVAILABLE
                continue
            rt.status = MONITOR_BOUND
            if device != configured.device_name:
                self._loginfo(f"Keeping {rt.rule.process_name} on {configured.device_name}")
                if not move_to_monitor_rect(rt.hwnd, configured):
                    rt.status = UNMOVABLE

    # ---- internals ---------------------------------------------------------

    def _fast_step(self, rt, now):
        if rt.phase in (PHASE_VERIFY, PHASE_MOVING):
            # A failed SetWindowPos verification keeps the phase in moving and
            # only schedules verify_at; re-check on that due time so the retry
            # / give-up path runs instead of freezing (spec §35, §36).
            if now >= rt.verify_at:
                self._after_move_check(rt, now)
            return
        # PHASE_SEARCH
        if rt.pid is None:
            return
        hwnd = find_main_window(rt.pid, rt.rule.process_name)
        if hwnd is None:
            if now > rt.deadline:
                rt.phase = PHASE_IDLE
                rt.status = WINDOW_MISSING
            else:
                rt.status = RUNNING
            return
        if rt.hwnd != hwnd:
            rt.hwnd = hwnd
            self._loginfo(f"Window found HWND 0x{hwnd:08X}")
        rt.status = WINDOW_FOUND
        if not rt.rule.move_on_start or self.paused:
            rt.phase = PHASE_IDLE
            return
        rt.attempts = 0
        rt.phase = PHASE_MOVING
        self._attempt_move(rt, now)

    def _attempt_move(self, rt, now):
        if rt.hwnd is None or not is_valid(rt.hwnd):
            # A dead HWND is a discovery problem, not a move failure (§23-25).
            self._lose_window(rt, now)
            return
        configured = self._resolve_monitor(rt)
        if configured is None:
            rt.phase = PHASE_IDLE
            rt.status = MONITOR_UNAVAILABLE
            self._logerror(rt, "assigned monitor unavailable")
            return
        self._loginfo(f"Moving {rt.rule.process_name} to {configured.device_name}")
        moved = move_to_monitor_rect(rt.hwnd, configured)
        rt.attempts += 1
        if moved:
            if rt.rule.maximize:
                maximize(rt.hwnd)
            rt.phase = PHASE_VERIFY
            rt.verify_at = now + VERIFY_DELAY
            rt.status = WINDOW_FOUND
        elif rt.attempts >= MAX_MOVE_ATTEMPTS:
            rt.phase = PHASE_GIVEN_UP
            rt.status = UNMOVABLE
            self._logerror(rt, f"window could not be moved after {MAX_MOVE_ATTEMPTS} attempts")
        else:
            rt.verify_at = now + VERIFY_DELAY
            self._log_move_failure(rt, configured)


    def _after_move_check(self, rt, now):
        if rt.hwnd is None or not is_valid(rt.hwnd):
            self._lose_window(rt, now)
            return
        configured = self._resolve_monitor(rt)
        if configured is None:
            rt.phase = PHASE_IDLE
            rt.status = MONITOR_UNAVAILABLE
            return
        device = window_monitor_device_name(rt.hwnd) if rt.hwnd else None
        if device == configured.device_name:
            rt.phase = PHASE_BOUND
            rt.status = MONITOR_BOUND
            self._loginfo(f"Application successfully bound to {configured.device_name}")
            return
        if rt.attempts < MAX_MOVE_ATTEMPTS:
            # Game reset its own position (spec §36) -> try again.
            rt.phase = PHASE_MOVING
            self._attempt_move(rt, now)
        else:
            rt.phase = PHASE_GIVEN_UP
            self._logerror(rt, f"window could not be moved after {MAX_MOVE_ATTEMPTS} attempts")

    def _reset(self, rt, status):
        rt.pid = None
        rt.hwnd = None
        rt.phase = PHASE_IDLE
        rt.attempts = 0
        rt.status = status

    def _lose_window(self, rt, now):
        """Stored HWND is dead: re-discover, this is not a move failure (§23-25, §50)."""
        self._loginfo(f"{rt.rule.process_name} window HWND gone, searching again")
        rt.hwnd = None
        rt.phase = PHASE_SEARCH
        rt.deadline = now + WINDOW_SEARCH_TIMEOUT
        rt.status = WINDOW_MISSING

    def _log_move_failure(self, rt, configured):
        """One diagnostic line per real failed move attempt (spec §49)."""
        if not self.log:
            return
        device = window_monitor_device_name(rt.hwnd) if rt.hwnd else None
        self.log.warning(
            f"{rt.rule.process_name} PID {rt.pid} HWND 0x{rt.hwnd:08X}: "
            f"move attempt {rt.attempts}/{MAX_MOVE_ATTEMPTS} failed, "
            f"target={configured.device_name}, current={device}, "
            f"maximized={is_maximized(rt.hwnd)}, phase={rt.phase}"
        )

    def _loginfo(self, message):
        if self.log:
            self.log.info(message)

    def _logerror(self, rt, message):
        if self.log:
            self.log.error(f"{rt.rule.process_name}: {message}")

    def _monitor_label(self, rt):
        stored = rt.rule.monitor
        for monitor in self.monitors:
            if monitor.device_name == stored.device_name:
                return monitor.label()
        return f"unavailable (stored: {stored.device_name})"

    def status_rows(self):
        return [
            (rt.rule.process_name, self._monitor_label(rt), rt.status)
            for rt in self.runtimes
        ]

    def emit_update(self):
        if self.on_update:
            self.on_update(self.status_rows())

    # ---- manual test (spec §31) --------------------------------------------

    def test_rule(self, index: int) -> str:
        rt = self.runtimes[index]
        if rt.pid is None:
            running = self.processes.tick()
            rt.pid = running.get(index)
            if rt.pid is None:
                return NOT_RUNNING
        hwnd = rt.hwnd
        if hwnd is None or not is_valid(hwnd):
            hwnd = find_main_window(rt.pid, rt.rule.process_name)
        if hwnd is None:
            return "Window not found"
        configured = self._resolve_monitor(rt)
        if configured is None:
            return MONITOR_UNAVAILABLE
        moved = move_to_monitor_rect(hwnd, configured)
        rt.hwnd = hwnd
        if moved:
            rt.phase = PHASE_BOUND
            rt.status = MONITOR_BOUND
            return "Success"
        rt.status = UNMOVABLE
        return UNMOVABLE
