"""
Modern reusable UI widgets for LAN-FT.
"""
import tkinter as tk
from tkinter import ttk
from ui.theme import get_palette
from services.i18n_service import t


class ModernButton(tk.Button):
    """Flat button with hover effect and rounded-like appearance via padding."""

    def __init__(self, parent, variant: str = "normal", **kw):
        self._variant = variant
        p = get_palette()
        bg, fg, hover = self._colors(p)
        super().__init__(
            parent,
            bg=bg, fg=fg,
            activebackground=hover, activeforeground=fg,
            relief="flat", bd=0,
            cursor="hand2",
            padx=16, pady=8,
            font=("Segoe UI Variable Text", 9),
            **kw,
        )
        self._bg = bg
        self._hover = hover
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _colors(self, p):
        if self._variant == "accent":
            return p["btn_accent_bg"], p["btn_accent_fg"], p["btn_accent_hover"]
        if self._variant == "danger":
            return p["btn_danger_bg"], p["btn_danger_fg"], p["btn_danger_hover"]
        return p["btn_bg"], p["btn_fg"], p["btn_hover"]

    def _on_enter(self, _e=None):
        self.configure(bg=self._hover)

    def _on_leave(self, _e=None):
        self.configure(bg=self._bg)

    def update_theme(self):
        p = get_palette()
        self._bg, fg, self._hover = self._colors(p)
        self.configure(bg=self._bg, fg=fg,
                       activebackground=self._hover, activeforeground=fg)


class Card(tk.Frame):
    """Elevated card container with optional title label and border."""

    def __init__(self, parent, title: str = "", **kw):
        p = get_palette()
        super().__init__(
            parent, bg=p["bg2"], 
            padx=16, pady=14, 
            highlightthickness=1,
            highlightbackground=p["border"],
            **kw
        )
        if title:
            self.title_label = tk.Label(
                self, text=title.upper(),
                bg=p["bg2"], fg=p["accent"],
                font=("Segoe UI Variable Display", 8, "bold"),
            )
            self.title_label.pack(anchor="w", pady=(0, 10))
        else:
            self.title_label = None

    def inner(self) -> "Card":
        """Return self for chaining."""
        return self


class RoundedProgressBar(tk.Canvas):
    """Smooth rounded progress bar drawn on a Canvas."""

    def __init__(self, parent, height: int = 8, **kw):
        p = get_palette()
        super().__init__(parent, height=height, bg=p["bg"],
                         highlightthickness=0, **kw)
        self._p = p
        self._value: float = 0.0
        self._mode = "determinate"
        self._anim_pos: float = 0.0
        self._anim_id = None
        self.bind("<Configure>", lambda _e: self._draw())

    def set(self, value: float) -> None:
        self._value = max(0.0, min(100.0, value))
        if self._mode == "determinate":
            self._draw()

    def start_indeterminate(self, interval: int = 40) -> None:
        self._mode = "indeterminate"
        self._anim_pos = 0.0
        self._animate(interval)

    def stop_indeterminate(self) -> None:
        self._mode = "determinate"
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None
        self._draw()

    def _animate(self, interval: int) -> None:
        if self._mode != "indeterminate":
            return
        self._anim_pos = (self._anim_pos + 2) % 120
        self._draw()
        self._anim_id = self.after(interval, lambda: self._animate(interval))

    def _draw(self) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4:
            return
        r = h // 2
        p = self._p
        # Track
        self._rrect(0, 0, w, h, r, p["bg2"])
        # Fill
        if self._mode == "indeterminate":
            seg = int(w * 0.35)
            x1 = int((self._anim_pos / 120) * (w + seg)) - seg
            x2 = x1 + seg
            x1 = max(0, x1)
            x2 = min(w, x2)
            if x2 > x1:
                self._rrect(x1, 0, x2, h, r, p["accent"])
        else:
            fill_w = int(w * self._value / 100)
            if fill_w >= r * 2:
                self._rrect(0, 0, fill_w, h, r, p["accent"])
            elif fill_w > 0:
                self.create_oval(0, 0, h, h, fill=p["accent"], outline="")

    def _rrect(self, x1, y1, x2, y2, r, color):
        self.create_arc(x1, y1, x1 + 2*r, y1 + 2*r, start=90,  extent=90,  style="pieslice", fill=color, outline="")
        self.create_arc(x2 - 2*r, y1, x2, y1 + 2*r, start=0,   extent=90,  style="pieslice", fill=color, outline="")
        self.create_arc(x1, y2 - 2*r, x1 + 2*r, y2, start=180, extent=90,  style="pieslice", fill=color, outline="")
        self.create_arc(x2 - 2*r, y2 - 2*r, x2, y2, start=270, extent=90,  style="pieslice", fill=color, outline="")
        self.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline="")
        self.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline="")


class ThemedDialog(tk.Toplevel):
    """Themed modal dialog replacing messagebox."""

    def __init__(self, parent, title: str, message: str,
                 buttons: tuple = ("OK",), icon: str = ""):
        super().__init__(parent)
        p = get_palette()
        self.configure(bg=p["bg"])
        self.title(title)
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.result: str | None = None

        # Icon + message
        msg_frame = tk.Frame(self, bg=p["bg"], padx=24, pady=20)
        msg_frame.pack(fill="x")
        if icon:
            tk.Label(msg_frame, text=icon, bg=p["bg"], fg=p["fg"],
                     font=("Segoe UI", 22)).pack(side="left", padx=(0, 14), anchor="n")
        tk.Label(msg_frame, text=message, bg=p["bg"], fg=p["fg"],
                 font=("Segoe UI", 10), wraplength=320,
                 justify="left").pack(side="left", anchor="w")

        # Separator
        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # Buttons
        btn_frame = tk.Frame(self, bg=p["bg2"], padx=16, pady=12)
        btn_frame.pack(fill="x")
        for i, label in enumerate(reversed(buttons)):
            variant = "accent" if i == 0 else "normal"
            ModernButton(
                btn_frame, text=label, variant=variant,
                command=lambda l=label: self._close(l),
            ).pack(side="right", padx=4)

        self._center(parent)
        self.wait_window()

    def _close(self, val: str) -> None:
        self.result = val
        self.destroy()

    def _center(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_x() + parent.winfo_width() // 2
        ph = parent.winfo_y() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{pw - w//2}+{ph - h//2}")


def themed_ask_yesno(parent, title: str, message: str) -> bool | None:
    """Drop-in replacement for messagebox.askyesno."""
    d = ThemedDialog(parent, title, message, buttons=(t("cancel_simple", "Скасувати"), t("no", "Ні"), t("yes", "Так")), icon="❓")
    if d.result == t("yes", "Так"):
        return True
    if d.result == t("no", "Ні"):
        return False
    return None


def themed_showerror(parent, title: str, message: str) -> None:
    """Drop-in replacement for messagebox.showerror."""
    ThemedDialog(parent, title, message, buttons=("OK",), icon="✘")


def themed_showwarning(parent, title: str, message: str) -> None:
    """Drop-in replacement for messagebox.showwarning."""
    ThemedDialog(parent, title, message, buttons=("OK",), icon="⚠")


def themed_askyesnocancel(parent, title: str, message: str) -> bool | None:
    """Drop-in replacement for messagebox.askyesnocancel."""
    d = ThemedDialog(parent, title, message, buttons=(t("cancel_simple", "Скасувати"), t("no", "Ні"), t("yes", "Так")), icon="❓")
    if d.result == t("yes", "Так"):
        return True
    if d.result == t("no", "Ні"):
        return False
    return None
