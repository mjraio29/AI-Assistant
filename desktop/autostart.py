"""
Cross-platform "launch Robert at login" toggle.

- macOS: writes a LaunchAgent plist to ~/Library/LaunchAgents
- Linux: writes a .desktop file to ~/.config/autostart
- Windows: writes a value under HKCU\\...\\Run

All three point at the packaged executable if `desktop/build.sh` has been
run (dist/Robert or dist/Robert.exe); otherwise they fall back to
`python -m desktop.main` from this project so autostart still works during
development, before you've built a standalone binary.
"""
import platform
import sys
from pathlib import Path

APP_NAME = "Robert"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _launch_command() -> list[str]:
    exe_unix = PROJECT_ROOT / "dist" / APP_NAME
    exe_win = PROJECT_ROOT / "dist" / f"{APP_NAME}.exe"
    if exe_unix.exists():
        return [str(exe_unix)]
    if exe_win.exists():
        return [str(exe_win)]
    return [sys.executable, "-m", "desktop.main"]


def _mac_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.robert.assistant.plist"


def _linux_desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / "robert.desktop"


def is_enabled() -> bool:
    system = platform.system()
    if system == "Darwin":
        return _mac_plist_path().exists()
    if system == "Linux":
        return _linux_desktop_path().exists()
    if system == "Windows":
        return _windows_run_key_exists()
    return False


def enable() -> None:
    system = platform.system()
    cmd = _launch_command()
    if system == "Darwin":
        _enable_macos(cmd)
    elif system == "Linux":
        _enable_linux(cmd)
    elif system == "Windows":
        _enable_windows(cmd)
    else:
        raise RuntimeError(f"Autostart isn't implemented for platform '{system}'")


def disable() -> None:
    system = platform.system()
    if system == "Darwin":
        _mac_plist_path().unlink(missing_ok=True)
    elif system == "Linux":
        _linux_desktop_path().unlink(missing_ok=True)
    elif system == "Windows":
        _disable_windows()


# --- macOS ------------------------------------------------------------

def _enable_macos(cmd: list[str]) -> None:
    path = _mac_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    args_xml = "\n".join(f"        <string>{c}</string>" for c in cmd)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.robert.assistant</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
"""
    path.write_text(plist)


# --- Linux --------------------------------------------------------------

def _enable_linux(cmd: list[str]) -> None:
    path = _linux_desktop_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    exec_line = " ".join(cmd)
    desktop_entry = f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Exec={exec_line}
X-GNOME-Autostart-enabled=true
"""
    path.write_text(desktop_entry)


# --- Windows --------------------------------------------------------------

_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _windows_run_key_exists() -> bool:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except FileNotFoundError:
        return False


def _enable_windows(cmd: list[str]) -> None:
    import winreg

    command = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)


def _disable_windows() -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
    except FileNotFoundError:
        pass
