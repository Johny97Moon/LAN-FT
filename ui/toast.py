"""
In-app toast notification with fade-in / fade-out animation.
"""
import tkinter as tk


class Toast:
    """Animated overlay toast that fades in, waits, then fades out."""

    def __init__(self, parent: tk.Tk | tk.Toplevel, message: str,
                 duration_ms: int = 3000):
        self._parent = parent
        self._message = message
        self._duration = duration_ms
        self._win: tk.Toplevel | None = None

    def show(self) -> None:
        if self._win:
            return
        self._win = tk.Toplevel(self._parent)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-alpha", 0.0)

        # Container with rounded feel via padding
        frame = tk.Frame(self._win, bg="#1e2030", padx=2, pady=2)
        frame.pack()
        inner = tk.Frame(frame, bg="#1e2030", padx=16, pady=10)
        inner.pack()
        tk.Label(
            inner,
            text=self._message,
            bg="#1e2030",
            fg="#e0e4f0",
            font=("Segoe UI", 10),
            wraplength=320,
            justify="left",
        ).pack()

        self._win.update_idletasks()
        self._position()
        self._fade_in()

    def _position(self) -> None:
        pw = self._parent.winfo_x() + self._parent.winfo_width()
        ph = self._parent.winfo_y() + self._parent.winfo_height()
        tw = self._win.winfo_width()
        th = self._win.winfo_height()
        self._win.geometry(f"+{pw - tw - 16}+{ph - th - 48}")

    def _fade_in(self, alpha: float = 0.0) -> None:
        alpha = min(alpha + 0.1, 0.92)
        try:
            self._win.attributes("-alpha", alpha)
        except (tk.TclError, AttributeError):
            return
        if alpha < 0.92:
            self._win.after(18, lambda: self._fade_in(alpha))
        else:
            self._win.after(self._duration, self._fade_out)

    def _fade_out(self, alpha: float = 0.92) -> None:
        alpha -= 0.08
        if alpha <= 0 or not self._win:
            if self._win:
                try:
                    self._win.destroy()
                except tk.TclError:
                    pass
                self._win = None
            return
        try:
            self._win.attributes("-alpha", alpha)
            self._win.after(35, lambda: self._fade_out(alpha))
        except tk.TclError:
            self._win = None


def show_toast(parent: tk.Tk | tk.Toplevel, message: str,
               duration_ms: int = 3000) -> None:
    Toast(parent, message, duration_ms).show()
