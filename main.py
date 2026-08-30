"""AnchorWin v1.0 entry point (spec §43, §37, §53).

Binds configured applications to their assigned monitors.
Local-only: no injection, no cloud, no telemetry, no admin rights.
"""
import ctypes
import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config import APP_TITLE, Config
from app.engine import RuleEngine
from app.gui import MainWindow
from app.logger import setup_logging
from app.tray import TrayController, icon_path

WINDOW_TITLE = APP_TITLE


def _set_dpi_awareness():
    """Per-monitor v2 DPI awareness so coordinates are physical pixels (§37).

    Uses the modern SetProcessDpiAwarenessContext; failures are ignored
    because Qt sets the same context by default when this cannot apply.
    """
    try:
        user32 = ctypes.windll.user32
        PER_MONITOR_V2 = ctypes.c_void_p(-4)
        user32.SetProcessDpiAwarenessContext(PER_MONITOR_V2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()


def _single_instance() -> bool:
    """True when this process may run; otherwise the first instance is shown."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, "AnchorWin_SingleInstance_Mutex")
    ERROR_ALREADY_EXISTS = 183
    if kernel32.GetLastError() != ERROR_ALREADY_EXISTS or not handle:
        return True
    # Bring the running instance's window forward, then exit (spec §43).
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if hwnd:
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
    return False


def main() -> int:
    _set_dpi_awareness()
    if not _single_instance():
        return 0
    QApplication.setApplicationName("AnchorWin")
    QApplication.setApplicationVersion("1.0")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(str(icon_path())))

    config = Config()
    log = setup_logging(config.dir / "logs", console=not getattr(sys, "frozen", False))
    log.info("Application started")
    if config.corrupt_fallback:
        log.error("config.json damaged; loaded config.json.bak instead")

    def _hook(exc_type, exc_value, exc_tb):
        log.error("Uncaught: " + "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))

    sys.excepthook = _hook

    engine = RuleEngine(
        config.data.rules, config.data.settings, log
    )
    window = MainWindow(config, engine, log)
    engine.on_update = window.refresh_table

    tray = TrayController(app, window, engine, window.reload_rules, log)
    window.tray_controller = tray

    def safe(kind, func):
        def runner():
            try:
                func()
                window.refresh_table()
            except Exception:
                log.error(f"{kind} tick failed: {traceback.format_exc()}")
        return runner

    proc_timer = QTimer(app)
    proc_timer.setInterval(1000)
    proc_timer.timeout.connect(safe("process", engine.proc_tick))
    proc_timer.start()

    fast_timer = QTimer(app)
    fast_timer.setInterval(250)
    fast_timer.timeout.connect(safe("fast", engine.fast_tick))
    keep_timer = QTimer(app)
    keep_timer.setInterval(700)
    keep_timer.timeout.connect(safe("keep", engine.keep_tick))

    def scheduler():
        if engine.needs_fast_ticker():
            if not fast_timer.isActive():
                fast_timer.start()
        else:
            fast_timer.stop()
        if engine.needs_keep_ticker():
            if not keep_timer.isActive():
                keep_timer.start()
        else:
            keep_timer.stop()

    schedule_timer = QTimer(app)
    schedule_timer.setInterval(500)
    schedule_timer.timeout.connect(scheduler)
    schedule_timer.start()

    monitor_timer = QTimer(app)
    monitor_timer.setInterval(5000)

    def refresh_monitors():
        try:
            engine.refresh_monitors()
            window.refresh_table()
        except Exception:
            log.error(f"monitor refresh failed: {traceback.format_exc()}")

    monitor_timer.timeout.connect(refresh_monitors)
    monitor_timer.start()

    scheduler()
    if config.data.settings.start_minimized:
        log.info("Start minimized to tray")
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
