"""
Dark / Light theme management for LAN-FT using sv-ttk.
"""
import tkinter as tk
from tkinter import ttk
import sv_ttk

# ── Palettes ─────────────────────────────────────────────────────────────────

DARK = {
    "bg":        "#1c1c1c",
    "bg2":       "#2c2c2c",
    "bg3":       "#3c3c3c",
    "fg":        "#ffffff",
    "fg_dim":    "#a0a0a0",
    "accent":    "#60cdff",
    "accent_fg": "#000000",
    "green":     "#6fdf8f",
    "red":       "#ff99a4",
    "yellow":    "#ffdb70",
    "border":    "#444444",
    "entry_bg":  "#242424",
    "select_bg": "#60cdff",
    "select_fg": "#000000",
    "btn_bg":    "#323232",
    "btn_fg":    "#ffffff",
    "btn_hover": "#3c3c3c",
    "btn_accent_bg":    "#60cdff",
    "btn_accent_fg":    "#000000",
    "btn_accent_hover": "#70dfff",
    "btn_danger_bg":    "#482323",
    "btn_danger_fg":    "#ff99a4",
    "btn_danger_hover": "#5a2d2d",
}

LIGHT = {
    "bg":        "#f3f3f3",
    "bg2":       "#ffffff",
    "bg3":       "#e5e5e5",
    "fg":        "#000000",
    "fg_dim":    "#666666",
    "accent":    "#005fb8",
    "accent_fg": "#ffffff",
    "green":     "#0f7b0f",
    "red":       "#c42b1c",
    "yellow":    "#9d5d00",
    "border":    "#cccccc",
    "entry_bg":  "#ffffff",
    "select_bg": "#005fb8",
    "select_fg": "#ffffff",
    "btn_bg":    "#ffffff",
    "btn_fg":    "#000000",
    "btn_hover": "#f9f9f9",
    "btn_accent_bg":    "#005fb8",
    "btn_accent_fg":    "#ffffff",
    "btn_accent_hover": "#0067c0",
    "btn_danger_bg":    "#fee2e2",
    "btn_danger_fg":    "#c42b1c",
    "btn_danger_hover": "#fecaca",
}

_current_palette: dict = DARK


def get_palette() -> dict:
    return _current_palette


def apply_theme(root: tk.Tk, mode: str = "dark") -> None:
    """Apply theme to root window. mode: 'dark' | 'light'"""
    global _current_palette
    p = DARK if mode == "dark" else LIGHT
    _current_palette = p

    # 1. Apply Sun Valley theme
    sv_ttk.set_theme(mode)

    # 2. Refine Ttk styles for our specifics
    style = ttk.Style(root)
    
    # Notebook tabs (Sv-ttk tabs are good, but we can refine padding)
    style.configure("TNotebook.Tab", padding=[20, 10])
    
    # Treeview tweaks
    style.configure("Treeview", rowheight=32)
    
    # Custom colors for status dots etc
    root.configure(bg=p["bg"])
    _apply_tk_colors(root, p)


def _apply_tk_colors(widget: tk.Widget, p: dict) -> None:
    """Recursively apply bg/fg to plain tk widgets."""
    cls = widget.winfo_class()
    try:
        # We skip most ttk-themed widgets as sv-ttk handles them
        if cls in ("Frame", "Toplevel", "Tk"):
            widget.configure(bg=p["bg"])
        elif cls == "Label":
            # Only labels not in treeview or special areas
            if "Treeview" not in str(widget):
                widget.configure(bg=p["bg"], fg=p["fg"])
        elif cls == "Entry":
            widget.configure(
                bg=p["entry_bg"], fg=p["fg"],
                insertbackground=p["fg"],
                relief="flat",
                highlightthickness=1,
                highlightbackground=p["border"],
                highlightcolor=p["accent"],
            )
        elif cls == "Text":
            widget.configure(bg=p["entry_bg"], fg=p["fg"], insertbackground=p["fg"])
        elif cls == "Listbox":
            widget.configure(
                bg=p["entry_bg"], fg=p["fg"],
                selectbackground=p["select_bg"],
                selectforeground=p["select_fg"],
                borderwidth=0,
                highlightthickness=1,
                highlightbackground=p["border"],
            )
        elif cls == "Canvas":
             widget.configure(bg=p["bg"], highlightthickness=0)
             
    except tk.TclError:
        pass

    for child in widget.winfo_children():
        _apply_tk_colors(child, p)
