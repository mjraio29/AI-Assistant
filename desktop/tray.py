"""
System tray icon for Robert. Runs pystray's icon loop in a background
thread; the main Tk window hides to tray on close instead of quitting, and
the tray menu can bring it back, toggle launch-at-login, or quit for real.
"""
import threading
from pathlib import Path

import pystray
from PIL import Image

from desktop import autostart

_ICON_PATH = Path(__file__).parent / "assets" / "icon.png"


class TrayIcon:
    def __init__(self, app):
        self.app = app  # the ChatApp (Tk root)
        self._icon: pystray.Icon | None = None

    def start(self):
        image = Image.open(_ICON_PATH)
        self._icon = pystray.Icon("robert", image, "Robert", menu=self._build_menu())
        threading.Thread(target=self._icon.run, daemon=True).start()

    def stop(self):
        if self._icon:
            self._icon.stop()

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("Show Robert", self._on_show, default=True),
            pystray.MenuItem("Start at login", self._on_toggle_autostart, checked=self._autostart_checked),
            pystray.MenuItem("Quit", self._on_quit),
        )

    def _autostart_checked(self, item) -> bool:
        try:
            return autostart.is_enabled()
        except Exception:
            return False

    def _on_show(self, icon, item):
        self.app.after(0, self._show_window)

    def _show_window(self):
        self.app.deiconify()
        self.app.lift()
        self.app.focus_force()

    def _on_toggle_autostart(self, icon, item):
        try:
            if autostart.is_enabled():
                autostart.disable()
            else:
                autostart.enable()
        except Exception:
            pass  # best-effort; unsupported platforms just no-op the toggle

    def _on_quit(self, icon, item):
        icon.stop()
        self.app.after(0, self.app.destroy)
