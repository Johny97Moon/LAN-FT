"""
System tray icon using pystray.
If pystray is not installed, tray is silently disabled.
"""
import threading
import tkinter as tk
from typing import Callable

try:
    import pystray
    from PIL import Image, ImageDraw
    _TRAY_AVAILABLE = True
except ImportError:
    _TRAY_AVAILABLE = False


def tray_available() -> bool:
    return _TRAY_AVAILABLE


def _make_icon_image(size: int = 64) -> "Image.Image":
    """Generate a simple coloured circle as tray icon (used when no .ico available)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, size - 4, size - 4), fill="#2196F3")
    draw.text((size // 2 - 6, size // 2 - 8), "LF", fill="white")
    return img


class TrayIcon:
    def __init__(
        self,
        root: tk.Tk,
        icon_path: str | None = None,
        on_show: Callable | None = None,
        on_quit: Callable | None = None,
        minimize_to_tray: bool = True,
    ):
        self._root = root
        self._icon_path = icon_path
        self._on_show = on_show or self._default_show
        self._on_quit = on_quit or self._default_quit
        self._minimize_to_tray = minimize_to_tray
        self._tray: "pystray.Icon | None" = None

    def setup(self) -> None:
        """Intercept window close → minimise to tray instead (if enabled)."""
        if not _TRAY_AVAILABLE:
            return
        self._root.protocol("WM_DELETE_WINDOW", self._hide_to_tray)

    def _hide_to_tray(self) -> None:
        # БАГ 15: якщо minimize_to_tray вимкнено — просто закриваємо
        if not self._minimize_to_tray:
            self._on_quit()
            return
        self._root.withdraw()
        if self._tray is None:
            self._start_tray()

    def _start_tray(self) -> None:
        if not _TRAY_AVAILABLE:
            return

        try:
            if self._icon_path:
                img = Image.open(self._icon_path)
            else:
                img = _make_icon_image()
        except Exception:
            img = _make_icon_image()

        menu = pystray.Menu(
            pystray.MenuItem("Відкрити", self._show_window, default=True),
            pystray.MenuItem("Вийти",   self._quit_app),
        )
        self._tray = pystray.Icon("LAN-FT", img, "LAN File Transfer", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _show_window(self, *_) -> None:
        self._root.after(0, self._on_show)

    def _quit_app(self, *_) -> None:
        if self._tray:
            self._tray.stop()
        self._root.after(0, self._on_quit)

    def _default_show(self) -> None:
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()

    def _default_quit(self) -> None:
        self._root.destroy()

    def stop(self) -> None:
        if self._tray:
            try:
                self._tray.stop()
            except Exception:
                pass
