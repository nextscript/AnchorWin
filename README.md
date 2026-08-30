# AnchorWin v1.0

**AnchorWin** is a small, lightweight Windows application with a graphical user interface that permanently binds applications to a specific monitor. It works completely locally — without DLL injection, hooks, cloud services, telemetry, or administrator privileges.

## How It Works

As soon as an EXE listed in the rules is started, AnchorWin automatically detects the process's main window and moves it to the configured monitor. The application runs continuously in the background via the system tray and automatically applies the saved rules — even after restarting the application or Windows, provided that **Autostart** is enabled.

## Running the Application

Run directly with Python (Python 3.12+ recommended):

```sh
pip install -r requirements.txt
python main.py
```

## Configuration File

The configuration is stored at `%APPDATA%\AnchorWin\config.json`.

Portable mode can be enabled by placing a `portable.flag` file in the application directory. In portable mode, the configuration file is stored next to the EXE.

A backup file (`config.json.bak`) is updated every time the configuration is saved. If the main configuration file becomes corrupted, AnchorWin automatically loads the backup copy.

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

## System Tray

* Tray icon — left-click to show or hide the application window
* Right-click menu: **Open**, **Pause Rules** (toggle), **Reload Rules**, **Exit**
* Closing the application window only hides it in the system tray
