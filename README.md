AnchorWin v1.0

AnchorWin is a small, lightweight Windows application with a GUI that permanently binds applications to a specific monitor. It runs entirely locally — without DLL injection, hooks, cloud services, telemetry, or administrator privileges.

How It Works

As soon as an EXE listed in the rules is launched, AnchorWin automatically detects the process's main window and moves it to the assigned monitor. AnchorWin runs continuously in the background (system tray) and automatically applies the saved rules — even after restarting the application or Windows, as long as Auto-start is enabled.

Running

Run directly with Python (Python 3.12+ recommended):

pip install -r requirements.txt
python main.py

System Tray

Tray icon (left-click or double-click: show/hide the window)

Right-click menu: Open, Pause Rules (toggle), Reload Rules, Exit

Closing the window only hides it (close window → system tray)

Configuration File

The configuration is stored at %APPDATA%\AnchorWin\config.json (portable mode is enabled via portable.flag in the application directory).
