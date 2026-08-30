"""Main window, rule table and dialogs for AnchorWin (spec §5–§7, §30–§33)."""
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import APP_TITLE, MonitorRef, Rule
from app.engine import MONITOR_UNAVAILABLE

MONITOR_TEXT_ROLE = Qt.UserRole + 1


class MonitorPreview(QWidget):
    """Clickable scaled rectangles laid out like the Windows arrangement (§30)."""

    def __init__(self, monitors, selected_index=0, parent=None):
        super().__init__(parent)
        self.monitors = monitors
        self.selected_index = selected_index
        self.setMinimumHeight(150)
        self.setMouseTracking(True)

    def _geometry(self):
        if not self.monitors:
            return None
        left = min(m.left for m in self.monitors)
        top = min(m.top for m in self.monitors)
        right = max(m.right for m in self.monitors)
        bottom = max(m.bottom for m in self.monitors)
        world_w = right - left
        world_h = bottom - top
        area = self.rect().adjusted(10, 10, -10, -10)
        scale = min(area.width() / world_w, area.height() / world_h) * 0.92
        ox = area.left() + (area.width() - world_w * scale) / 2
        oy = area.top() + (area.height() - world_h * scale) / 2
        return left, top, scale, ox, oy

    def rect_for(self, monitor):
        geom = self._geometry()
        if geom is None:
            return None
        left, top, scale, ox, oy = geom
        x = ox + (monitor.left - left) * scale
        y = oy + (monitor.top - top) * scale
        w = max(int(monitor.width * scale), 24)
        h = max(int(monitor.height * scale), 18)
        return QRect(int(x), int(y), w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for monitor in self.monitors:
            rect = self.rect_for(monitor)
            if rect is None:
                continue
            selected = monitor.index == self.selected_index
            painter.setPen(QPen(QColor(30, 30, 30)))
            painter.setBrush(
                QColor(60, 110, 180, 220) if selected else QColor(235, 235, 235, 235)
            )
            painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(QColor(255, 255, 255) if selected else QColor(40, 40, 40))
            label = f"Monitor {monitor.index}"
            text_rect = rect.adjusted(4, 2, -4, -2)
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, label)
            sub = monitor.resolution + (" (Primary)" if monitor.is_primary else "")
            painter.drawText(text_rect, Qt.AlignHCenter | Qt.AlignVCenter, sub)
        painter.end()

    def mousePressEvent(self, event):
        for monitor in self.monitors:
            rect = self.rect_for(monitor)
            if rect is not None and rect.contains(event.position().toPoint()):
                self.selected_index = monitor.index
                self.update()
                if self.on_select is not None:
                    self.on_select(monitor.index)
                return
        super().mousePressEvent(event)

    on_select = None


class RuleDialog(QDialog):
    """Add/Edit dialog (spec §6, §7, §30, §32)."""

    def __init__(self, monitors, rule=None, parent=None):
        super().__init__(parent)
        self.monitors = monitors
        self.rule = rule
        self.setWindowTitle("Add Application" if rule is None else "Edit Application")
        self.setModal(True)

        form = QFormLayout(self)
        self.running_combo = QComboBox(self)
        self._populate_running()
        self.running_combo.currentIndexChanged.connect(self._picked_running)
        self.exe_edit = QLineEdit(self)
        self.exe_edit.setReadOnly(True)
        browse = QPushButton("Select EXE …")
        browse.clicked.connect(self._browse)
        exe_row = QHBoxLayout()
        exe_row.addWidget(self.exe_edit)
        exe_row.addWidget(browse)

        self.proc_label = QLabel(self)
        self.proc_label.setText("<i>set automatically</i>")
        self.monitor_combo = QComboBox(self)
        for monitor in monitors:
            self.monitor_combo.addItem(monitor.label(), monitor.index)

        self.preview = MonitorPreview(monitors)
        self.preview.on_select = self._select_from_preview

        self.move_check = QCheckBox("Move when application starts")
        self.keep_check = QCheckBox("Keep on assigned monitor")
        self.max_check = QCheckBox("Maximize after moving")
        self.move_check.setChecked(True)
        self.keep_check.setChecked(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        form.addRow("Running Application:", self.running_combo)
        form.addRow("Application:", exe_row)
        form.addRow("Process:", self.proc_label)
        form.addRow("Monitor:", self.monitor_combo)
        form.addRow(self.preview)
        form.addRow(self.move_check)
        form.addRow(self.keep_check)
        form.addRow(self.max_check)
        form.addRow(buttons)
        self.monitor_combo.currentIndexChanged.connect(self._select_from_combo)

        if rule is not None:
            self.exe_edit.setText(rule.path)
            self.proc_label.setText(rule.process_name)
            index = self._monitor_index_for(rule.monitor)
            combo_pos = self.monitor_combo.findData(index)
            if combo_pos >= 0:
                self.monitor_combo.setCurrentIndex(combo_pos)
            self.preview.selected_index = index
            self.preview.update()
            self.move_check.setChecked(rule.move_on_start)
            self.keep_check.setChecked(rule.keep_on_monitor)
            self.max_check.setChecked(rule.maximize)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Application", "", "Executable Files (*.exe)"
        )
        if path:
            self.exe_edit.setText(path)
            name = path.replace("\\", "/").rsplit("/", 1)[-1]
            self.proc_label.setText(name)

    def _populate_running(self):
        from app.process_monitor import running_applications

        self.running_combo.blockSignals(True)
        self.running_combo.clear()
        self.running_combo.addItem("(please choose)", "")
        for name, exe in running_applications():
            self.running_combo.addItem(name, exe)
        self.running_combo.blockSignals(False)

    def _picked_running(self):
        exe = self.running_combo.currentData()
        if exe:
            self.exe_edit.setText(exe)
            self.proc_label.setText(exe.replace("\\", "/").rsplit("/", 1)[-1])
        elif self.rule is None:
            self.exe_edit.clear()
            self.proc_label.setText("<i>set automatically</i>")

    def _monitor_index_for(self, stored: MonitorRef):
        for monitor in self.monitors:
            if monitor.device_name == stored.device_name:
                return monitor.index
        return stored.monitor_index

    def _select_from_combo(self):
        index = self.monitor_combo.currentData()
        self.preview.selected_index = index
        self.preview.update()

    def _select_from_preview(self, index):
        combo_pos = self.monitor_combo.findData(index)
        if combo_pos >= 0:
            self.monitor_combo.setCurrentIndex(combo_pos)

    def _accept(self):
        path = self.exe_edit.text().strip()
        if not path:
            QMessageBox.warning(self, APP_TITLE, "Select an .exe file first.")
            return
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        index = self.monitor_combo.currentData()
        monitor = None
        for candidate in self.monitors:
            if candidate.index == index:
                monitor = candidate
                break
        if monitor is None:
            QMessageBox.warning(self, APP_TITLE, "Select a monitor first.")
            return
        self.saved_rule = Rule(
            path=path,
            process_name=name,
            monitor=MonitorRef(
                monitor_index=monitor.index,
                device_name=monitor.device_name,
                resolution=monitor.resolution,
                position=(monitor.left, monitor.top, monitor.right, monitor.bottom),
            ),
            move_on_start=self.move_check.isChecked(),
            keep_on_monitor=self.keep_check.isChecked(),
            maximize=self.max_check.isChecked(),
        )
        super().accept()

    saved_rule = None


class MainWindow(QMainWindow):
    """Rule table window (spec §5) wired to config and engine."""

    def __init__(self, config, engine, log):
        super().__init__()
        self.config = config
        self.engine = engine
        self.log = log
        self.setWindowTitle(APP_TITLE)
        self.setObjectName("AnchorWinMainWindow")

        central = QWidget(self)
        layout = QVBoxLayout(central)
        self.table = QTableWidget(0, 3, central)
        self.table.setHorizontalHeaderLabels(["Application", "Monitor", "Status"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.cellDoubleClicked.connect(self._edit_selected)
        layout.addWidget(self.table)

        button_row = QHBoxLayout()
        self.add_button = QPushButton("Add Application", central)
        self.edit_button = QPushButton("Edit", central)
        self.delete_button = QPushButton("Delete", central)
        self.test_button = QPushButton("Test", central)
        self.add_button.clicked.connect(self._add)
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button.clicked.connect(self._delete_selected)
        self.test_button.clicked.connect(self._test_selected)
        for button in (self.add_button, self.edit_button, self.delete_button, self.test_button):
            button_row.addWidget(button)
        layout.addLayout(button_row)

        self.autostart_check = QCheckBox("Start with Windows", central)
        self.keep_check = QCheckBox("Keep application on assigned monitor", central)
        self.minimized_check = QCheckBox("Start minimized to tray", central)
        layout.addWidget(self.autostart_check)
        layout.addWidget(self.keep_check)
        layout.addWidget(self.minimized_check)
        self.autostart_check.toggled.connect(self._autostart_toggled)
        self.keep_check.toggled.connect(self._keep_toggled)
        self.minimized_check.toggled.connect(self._minimized_toggled)

        self.setCentralWidget(central)
        self._load_from_config()
        self.refresh_table()

    # ---- state ------------------------------------------------------------

    def _load_from_config(self):
        from app import autostart

        settings = self.config.data.settings
        self.blockSignals(True)
        self.autostart_check.blockSignals(True)
        self.keep_check.blockSignals(True)
        self.minimized_check.blockSignals(True)
        self.autostart_check.setChecked(autostart.is_enabled())
        self.keep_check.setChecked(settings.keep_all_on_monitor)
        self.minimized_check.setChecked(settings.start_minimized)
        self.autostart_check.blockSignals(False)
        self.keep_check.blockSignals(False)
        self.minimized_check.blockSignals(False)

    def refresh_table(self):
        rows = self.engine.status_rows()
        self.table.setRowCount(len(rows))
        for i, (name, monitor_label, status) in enumerate(rows):
            stored = self.config.data.rules[i].monitor if i < len(self.config.data.rules) else None
            for col, text in enumerate((name, monitor_label, status)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if stored is not None:
                    item.setData(MONITOR_TEXT_ROLE, stored.device_name)
                self.table.setItem(i, col, item)

    def _selected_row(self):
        row = self.table.currentRow()
        return row if row >= 0 else None

    # ---- actions -----------------------------------------------------------

    def _add(self):
        dialog = RuleDialog(self.engine.monitors, parent=self)
        if dialog.exec() != QDialog.Accepted or dialog.saved_rule is None:
            return
        self.config.add_rule(dialog.saved_rule)
        self.engine.set_rules(self.config.data.rules)
        self.refresh_table()

    def _edit_selected(self):
        row = self._selected_row()
        if row is None:
            return
        current = self.config.data.rules[row]
        dialog = RuleDialog(self.engine.monitors, current, parent=self)
        if dialog.exec() != QDialog.Accepted or dialog.saved_rule is None:
            return
        self.config.update_rule(row, dialog.saved_rule)
        self.engine.set_rules(self.config.data.rules)
        self.refresh_table()

    def _delete_selected(self):
        row = self._selected_row()
        if row is None:
            return
        rule = self.config.data.rules[row]
        answer = QMessageBox.question(
            self,
            APP_TITLE,
            f"Delete rule for {rule.process_name}? The application itself is kept.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.config.delete_rule(row)
        self.engine.set_rules(self.config.data.rules)
        self.refresh_table()

    def _test_selected(self):
        row = self._selected_row()
        if row is None:
            return
        result = self.engine.test_rule(row)
        self.refresh_table()
        self.statusBar().showMessage(f"Test: {result}", 5000)

    def reload_rules(self):
        self.config.load()
        self.engine.set_rules(self.config.data.rules)
        self._load_from_config()
        self.refresh_table()

    # ---- settings toggles (spec §19: save immediately) ---------------------

    def _autostart_toggled(self, checked):
        from app import autostart

        ok = autostart.set_enabled(checked)
        self.config.data.settings.autostart = checked
        self.config.save_settings()
        if not ok:
            QMessageBox.warning(
                self,
                APP_TITLE,
                "Could not write the autostart registry entry.",
            )

    def _keep_toggled(self, checked):
        self.config.data.settings.keep_all_on_monitor = checked
        self.config.save_settings()

    def _minimized_toggled(self, checked):
        self.config.data.settings.start_minimized = checked
        self.config.save_settings()

    # ---- tray behaviour (spec §21) ------------------------------------------

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        if not hasattr(self, "_tray_hint_shown"):
            self._tray_hint_shown = True
            controller = getattr(self, "tray_controller", None)
            if controller is not None:
                controller.tray.showMessage(
                    APP_TITLE,
                    "Still running in the tray. Use Exit in the tray menu to quit.",
                )
