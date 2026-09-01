<p align="center"><img src="https://raw.githubusercontent.com/nextscript/AnchorWin/refs/heads/main/logo.png"></p>

# AnchorWin v1.0.2

**AnchorWin** is a small, lightweight Windows program with a GUI that permanently binds applications to a specific monitor. It works entirely locally — no DLL injection, no hooks, no cloud, no telemetry, and no administrator rights.

## How it works

As soon as a configured EXE is started, AnchorWin automatically detects the process's main window and moves it to the stored monitor. The program runs permanently in the background (system tray) and applies the saved rules automatically — also after restarting the program and Windows, as long as "Autostart" is enabled.

## Adding an application (both ways)

When creating or editing an application rule, there are two equivalent selection paths:

1. **From currently running applications**: the "Running Application" dropdown lists every process with a readable program path; click an entry and the rule takes over window + program automatically.
2. **Manually via EXE selection**: with the "Select EXE …" button (file dialog) you can select any .exe, even if it is not running right now.

Both paths fill the same rule fields; the manual selection remains fully intact.

## Settings file

Configuration lives under `%APPDATA\AnchorWin\config.json` (portable mode: `portable.flag` in the program folder → settings are stored next to the EXE). A backup copy (`config.json.bak`) is updated on every save; if the main file is damaged, the backup copy is reloaded automatically.

### Example

```json
{
 "applications": [
  {
   "path": "C:\\Games\\SHProto\\SHProto-Win64-Shipping.exe",
   "process_name": "SHProto-Win64-Shipping.exe",
   "monitor": {
    "monitor_index": 1,
    "device_name": "\\\\.\\DISPLAY1",
    "resolution": "2560x1440",
    "position": [0, 0, 2560, 1440]
   },
   "move_on_start": true,
   "keep_on_monitor": true,
   "maximize": false
  }
 ],
 "settings": {
  "autostart": false,
  "keep_all_on_monitor": true,
  "start_minimized": false
 }
}
```

## System tray

- Icon in the tray (left click: show/hide)
- Right-click menu: *Open*, *Pause Rules* (toggle), *Reload Rules*, *Exit*
- Closing the window only hides the window in the tray
