"""System tray icon and menu (spec §21, §22)."""
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu
from PySide6.QtWidgets import QSystemTrayIcon

from app.config import APP_TITLE


def icon_path() -> Path:
    root = Path(__file__).resolve().parent.parent
    bundle = root / "icon.ico"
    try:
        meipass = Path(sys._MEIPASS)  # set by PyInstaller onefile builds
    except AttributeError:
        return bundle
    cand = meipass / "icon.ico"
    return cand if cand.exists() else bundle


class TrayController:
    """Wraps QSystemTrayIcon; Open / Pause Rules / Reload Rules / Exit."""

    def __init__(self, app, main_window, engine, on_reload, log=None):
        self.app = app
        self.main_window = main_window
        self.engine = engine
        self.on_reload = on_reload
        self.log = log

        icon = QIcon(str(icon_path()))
        if icon.isNull():
            icon = app.windowIcon()
        self.icon = icon
        self.menu = QMenu()
        self.open_action = self.menu.addAction("Open")
        self.open_action.triggered.connect(self._show_window)
        self.pause_action = self.menu.addAction("Pause Rules")
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self._toggle_pause)
        self.reload_action = self.menu.addAction("Reload Rules")
        self.reload_action.triggered.connect(self._reload)
        self.menu.addSeparator()
        self.exit_action = self.menu.addAction("Exit")
        self.exit_action.triggered.connect(self._quit)

        self.tray = QSystemTrayIcon(icon, app)
        self.tray.setToolTip(APP_TITLE)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self.tray.show()

    def _activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.main_window.isVisible():
                self.main_window.hide()
            else:
                self._show_window()

    def _show_window(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _toggle_pause(self, checked):
        self.engine.paused = checked
        self.main_window.statusBar().showMessage(
            "Rules paused" if checked else "Rules active", 4000
        )

    def _reload(self):
        self.on_reload()

    def _quit(self):
        self.engine.paused = True
        QApplication.quit()
