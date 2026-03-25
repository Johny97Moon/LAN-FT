import os
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from transfer.manager import TransferManager
from transfer.queue import QueueJob
from config.settings import load_settings, save_settings, get_base_dir
from models.file_info import TransferProgress
from net.crypto import crypto_available
from services.firewall_service import add_firewall_rule, check_rule_exists
from services.history_service import load_history, clear_history
from services.ip_service import get_local_ip
from services.keyring_service import load_psk, keyring_available
from services.log_service import get_logger, reconfigure
from services.i18n_service import t
from ui.callbacks import on_job_update, on_recv_progress, on_host_status
from ui.constants import SPEED_PRESETS, fmt_speed
from ui.theme import apply_theme, get_palette
from ui.tray import TrayIcon, tray_available
from ui.settings_dialog import SettingsDialog
from ui.widgets import (
    ModernButton, Card, RoundedProgressBar,
    themed_showerror, themed_showwarning,
    themed_ask_yesno, themed_askyesnocancel,
)

_log = get_logger("lan_ft.ui")


# ── Drag & drop helper (tkinterdnd2 optional) ────────────────────────────────

def _try_enable_dnd(widget, callback):
    """Bind drag-and-drop if tkinterdnd2 is available."""
    try:
        widget.drop_target_register("DND_Files")  # type: ignore[attr-defined]
        widget.dnd_bind("<<Drop>>", callback)      # type: ignore[attr-defined]
        return True
    except Exception:
        return False


def _parse_dnd_data(data: str) -> list[str]:
    """Parse tkinterdnd2 drop data into a list of paths."""
    import re
    # Paths may be space-separated or wrapped in braces
    paths = re.findall(r'\{([^}]+)\}|(\S+)', data)
    return [a or b for a, b in paths]


class MainWindow:
    def __init__(self):
        self.settings = load_settings()
        self._translatable_widgets: list[tuple] = []
        reconfigure(self.settings.get("log_level", "INFO"))
        _log.info("LAN-FT starting up.")

        self.manager = TransferManager()
        self.manager.queue.on_job_update = self._on_job_update
        self.is_hosting = False
        self._queue_file_paths: list[str] = []
        
        # Performance: Batch UI updates to reduce redraws (CPU/GPU optimization)
        self._ui_update_queue: dict[str, dict] = {}
        self._ui_cache: dict[str, tuple] = {}
        self._ui_update_lock = threading.Lock()

        # Load PSK: prefer keyring
        self._psk_value = load_psk() or self.settings.get("psk", "")

        # Try to use tkinterdnd2 for drag & drop
        try:
            from tkinterdnd2 import TkinterDnD
            self.root = TkinterDnD.Tk()
            self._dnd_available = True
        except Exception:
            self.root = tk.Tk()
            self._dnd_available = False

        self.root.title("LAN File Transfer")
        self.root.resizable(True, True)
        self.root.minsize(560, 480)
        # Global font defaults
        self.root.option_add("*Font", "\"Segoe UI\" 10")
        self.root.option_add("*TButton.Padding", "8 4")

        # Set window icon
        icon_path = str(get_base_dir() / "resources" / "app.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except Exception:
                pass

        self._build_ui()
        # Apply theme after UI is built so all widgets exist
        self._theme_mode = self.settings.get("theme", "dark")
        apply_theme(self.root, self._theme_mode)
        self._check_firewall()
        self._schedule_ui_update()

        # Tray
        icon_path = str(get_base_dir() / "resources" / "app.ico")
        self._tray = TrayIcon(
            self.root,
            icon_path=icon_path if os.path.exists(icon_path) else None,
            on_show=self._show_window,
            on_quit=self._quit,
            minimize_to_tray=self.settings.get("minimize_to_tray", True),
        )
        self._tray.setup()

    # ── Retranslation ────────────────────────────────────────────────────────

    def _reg(self, widget, key, default=None, attr="text", *args, **kwargs):
        """Register a widget for retranslation and return initial text."""
        self._translatable_widgets.append((widget, attr, key, default, args, kwargs))
        val = t(key, default)
        prefix = kwargs.get("prefix", "")
        suffix = kwargs.get("suffix", "")
        res = f"{prefix}{val}{suffix}"
        return res.upper() if "upper" in kwargs else res

    def _retranslate_ui(self):
        """Update all registered widgets with new translations."""
        for widget, attr, key, default, args, kwargs in self._translatable_widgets:
            if not widget: continue
            try:
                val = t(key, default)
                prefix = kwargs.get("prefix", "")
                suffix = kwargs.get("suffix", "")
                final_text = f"{prefix}{val}{suffix}"
                if "upper" in kwargs: final_text = final_text.upper()

                if attr == "text":
                    widget.config(text=final_text)
                elif attr == "tab_text":
                    widget.tab(args[0], text=final_text)
                elif attr == "column_heading":
                    widget.heading(args[0], text=final_text)
                elif attr == "card_title":
                    if hasattr(widget, "title_label") and widget.title_label:
                        widget.title_label.config(text=final_text)
            except Exception:
                pass
        
        # Manual updates for dynamic elements
        # Host button
        if self.is_hosting:
            self.host_btn.config(text=t("stop_hosting", "⏹  Зупинити прийом"))
        else:
            self.host_btn.config(text=t("start_hosting", "▶  Почати прийом"))
        
        # IP Display
        self.ip_var.set(f"IP: {get_local_ip()}")
        
        # Speed limit combo values
        from ui.constants import SPEED_PRESETS
        unl_str = t("speed_unlimited", "Без обмежень")
        new_vals = [unl_str] + [k for k in SPEED_PRESETS.keys() if k != "Без обмежень"]
        self._speed_combo.config(values=new_vals)
        # If current value was the previous "unlimited" string, update it
        if self.speed_limit_var.get() in ("Без обмежень", "Unlimited"):
            self.speed_limit_var.set(unl_str)

        # Status Bar initial state
        cur_status = self.status_var.get()
        if cur_status in ("Готовий", "Ready", "готов", "ready"):
            self.status_var.set(t("status_ready", "Готовий"))

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        """Monolithic layout split into modular methods."""
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        self._build_top_bar()
        self._build_tabs()
        self._build_status_bar()

    def _build_top_bar(self):
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=16, pady=(16, 8))

        # IP display
        self.ip_var = tk.StringVar(value=f"IP: {get_local_ip()}")
        ttk.Label(top, textvariable=self.ip_var, font=("Segoe UI Variable Text", 10, "bold")).pack(side="left")

        # PSK logic
        psk_lbl = ttk.Label(top, text=self._reg(None, "PSK:", "  PSK:"), font=("Segoe UI Variable Text", 9))
        psk_lbl.pack(side="left", padx=(10, 0))
        self._reg(psk_lbl, "  PSK:")
        
        self.psk_var = tk.StringVar(value=self._psk_value)
        psk_entry = ttk.Entry(top, textvariable=self.psk_var, width=20, show="*")
        psk_entry.pack(side="left", padx=4)
        
        self.show_psk = tk.BooleanVar()
        self.psk_toggle = ttk.Checkbutton(top, text="👁", variable=self.show_psk, style="Toggle.TButton",
                       command=lambda: psk_entry.config(
                           show="" if self.show_psk.get() else "*"))
        self.psk_toggle.pack(side="left")

        # Global Actions
        actions = ttk.Frame(top)
        actions.pack(side="right")
        
        hint = "🔒 AES" if crypto_available() else "⚠ Clear"
        self.hint_lbl = ttk.Label(actions, text=hint, font=("Segoe UI Variable Text", 9))
        self.hint_lbl.pack(side="left", padx=8)
        
        self.theme_btn = ModernButton(actions, text="🌓", command=self._toggle_theme, width=3)
        self.theme_btn.pack(side="left", padx=4)
        
        self.settings_btn = ModernButton(actions, text="⚙", command=self._open_settings, width=3)
        self.settings_btn.pack(side="left", padx=4)

    def _build_tabs(self):
        pad = {"padx": 10, "pady": 4}
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        self._tab_host    = ttk.Frame(nb)
        self._tab_send    = ttk.Frame(nb)
        self._tab_queue   = ttk.Frame(nb)
        self._tab_history = ttk.Frame(nb)

        self._main_nb = nb
        nb.add(self._tab_host,    text=self._reg(nb, "tab_host", "  Host  ", "tab_text", 0, prefix="  ", suffix="  "))
        nb.add(self._tab_send,    text=self._reg(nb, "tab_send", "  Send  ", "tab_text", 1, prefix="  ", suffix="  "))
        nb.add(self._tab_queue,   text=self._reg(nb, "tab_queue", "  Queue  ", "tab_text", 2, prefix="  ", suffix="  "))
        nb.add(self._tab_history, text=self._reg(nb, "tab_history", "  History  ", "tab_text", 3, prefix="  ", suffix="  "))

        self._build_host_tab(pad)
        self._build_send_tab(pad)
        self._build_queue_tab(pad)
        self._build_history_tab(pad)

    def _build_status_bar(self):
        ttk.Separator(self.root, orient="horizontal").pack(fill="x", side="bottom")
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", side="bottom", padx=12, pady=6)
        
        self._status_dot = ttk.Label(bar, text="●", foreground=get_palette()["green"], font=("Segoe UI Variable Text", 10))
        self._status_dot.pack(side="left", padx=(0, 6))
        
        self.status_var = tk.StringVar(value=t("status_ready", "Готовий"))
        status_lbl = ttk.Label(bar, textvariable=self.status_var, font=("Segoe UI Variable Text", 9))
        status_lbl.pack(side="left")
        # Note: status_var itself is updated in callbacks, but some static states are set here
        
        self.speed_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.speed_var, font=("Consolas", 9)).pack(side="right", padx=10)
        
        if tray_available():
            ttk.Label(bar, text="Tray 🔽", font=("Segoe UI Variable Text", 8)).pack(side="right")

    # ── Host tab ─────────────────────────────────────────────────────────────

    def _build_host_tab(self, pad):
        f = self._tab_host

        title_txt = self._reg(None, "server_settings", "Налаштування сервера", upper=True)
        card = Card(f, title=title_txt)
        card.pack(fill="x", padx=16, pady=16)
        self._reg(card, "server_settings", attr="card_title", upper=True)

        row = ttk.Frame(card)
        row.pack(fill="x", pady=8)
        lbl_port = ttk.Label(row, text=self._reg(None, "port", "Порт:"), width=8)
        lbl_port.pack(side="left")
        self._reg(lbl_port, "port")
        self.port_var = tk.StringVar(value=str(self.settings.get("port", 5001)))
        ttk.Entry(row, textvariable=self.port_var, width=10).pack(side="left", padx=10)

        row2 = ttk.Frame(card)
        row2.pack(fill="x", pady=8)
        lbl_save = ttk.Label(row2, text=self._reg(None, "save_to", "Зберігати в:"), width=12)
        lbl_save.pack(side="left")
        self._reg(lbl_save, "save_to")
        self.save_dir_var = tk.StringVar(value=self.settings.get("save_dir", ""))
        ttk.Entry(row2, textvariable=self.save_dir_var).pack(side="left", fill="x", expand=True, padx=10)
        ModernButton(row2, text="…", command=self._choose_save_dir, width=3).pack(side="left")

        info_frame = ttk.Frame(f)
        info_frame.pack(fill="both", expand=True, padx=16)
        
        self.host_status_var = tk.StringVar(value=t("host_not_active", "Не активний"))
        ttk.Label(info_frame, textvariable=self.host_status_var, font=("Segoe UI Variable Text", 11)).pack(pady=20)

        ctrl = ttk.Frame(f)
        ctrl.pack(side="bottom", pady=20)
        self.host_btn = ModernButton(
            ctrl, text=self._reg(None, "start_hosting", "▶  Почати прийом"), variant="accent",
            command=self._toggle_hosting,
        )
        self.host_btn.pack(side="left", padx=8)
        self._reg(self.host_btn, "start_hosting")
        
        self.firewall_btn = ModernButton(ctrl, text=self._reg(None, "firewall_btn", "🔓 Брандмауер"),
                     command=self._open_firewall)
        self.firewall_btn.pack(side="left", padx=8)
        self._reg(self.firewall_btn, "firewall_btn")

    # ── Send tab ─────────────────────────────────────────────────────────────

    def _build_send_tab(self, pad):
        f = self._tab_send

        # Target card
        target_card = Card(f, title=self._reg(None, "receiver", "Отримувач", upper=True))
        target_card.pack(fill="x", padx=16, pady=(16, 8))
        self._reg(target_card, "receiver", attr="card_title", upper=True)

        target_row = ttk.Frame(target_card)
        target_row.pack(fill="x", pady=4)
        lbl_ip = ttk.Label(target_row, text=self._reg(None, "host_ip", "IP хоста:"))
        lbl_ip.pack(side="left")
        self._reg(lbl_ip, "host_ip")
        self.target_ip_var = tk.StringVar()
        ttk.Entry(target_row, textvariable=self.target_ip_var, width=16).pack(side="left", padx=8)
        
        lbl_port_send = ttk.Label(target_row, text=self._reg(None, "port", "Порт:"))
        lbl_port_send.pack(side="left", padx=(10, 0))
        self._reg(lbl_port_send, "port")
        self.send_port_var = tk.StringVar(value=str(self.settings.get("port", 5001)))
        ttk.Entry(target_row, textvariable=self.send_port_var, width=8).pack(side="left", padx=8)
        
        self.find_btn = ModernButton(target_row, text=self._reg(None, "find_btn", "🔍 Знайти"),
                     command=self._discover, width=8)
        self.find_btn.pack(side="right")
        self._reg(self.find_btn, "find_btn")

        disc_card = Card(f, title=self._reg(None, "found_hosts", "Знайдені хости", upper=True))
        disc_card.pack(fill="x", padx=16, pady=8)
        self._reg(disc_card, "found_hosts", attr="card_title", upper=True)
        self.disc_listbox = tk.Listbox(disc_card, height=3, selectmode="single")
        self.disc_listbox.pack(fill="x", pady=4)
        self.disc_listbox.bind("<<ListboxSelect>>", self._on_disc_select)
        self._disc_hosts: list[dict] = []

        # Files card
        files_card = Card(f, title=self._reg(None, "files_folders", "Файли / папки", upper=True))
        files_card.pack(fill="both", expand=True, padx=16, pady=8)
        self._reg(files_card, "files_folders", attr="card_title", upper=True)

        btn_row = ttk.Frame(files_card)
        btn_row.pack(fill="x", pady=(0, 10))
        self.add_file_btn = ModernButton(btn_row, text=self._reg(None, "add_file", "+ Файл"),   command=self._add_files)
        self.add_file_btn.pack(side="left", padx=(0, 6))
        self._reg(self.add_file_btn, "add_file")
        self.add_folder_btn = ModernButton(btn_row, text=self._reg(None, "add_folder", "+ Папка"),  command=self._add_folder)
        self.add_folder_btn.pack(side="left", padx=6)
        self._reg(self.add_folder_btn, "add_folder")
        self.remove_btn = ModernButton(btn_row, text=self._reg(None, "remove_btn", "✖ Видалити"), variant="danger",
                     command=self._remove_selected_file)
        self.remove_btn.pack(side="right")
        self._reg(self.remove_btn, "remove_btn")
        
        dnd_hint = "← " + (t("drop_hint", "перетягніть") if self._dnd_available else "(install tkinterdnd2)")
        ttk.Label(btn_row, text=dnd_hint, font=("Segoe UI Variable Text", 8)).pack(side="left", padx=12)

        self.files_listbox = tk.Listbox(files_card, height=4, selectmode="extended")
        self.files_listbox.pack(fill="both", expand=True, pady=4)

        if self._dnd_available:
            _try_enable_dnd(self.files_listbox, self._on_drop)
            _try_enable_dnd(files_card, self._on_drop)

        opts_row = ttk.Frame(f)
        opts_row.pack(fill="x", padx=16, pady=8)
        speed_lbl = ttk.Label(opts_row, text=self._reg(None, "speed", "Швидкість:"))
        speed_lbl.pack(side="left")
        self._reg(speed_lbl, "speed")
        self.speed_limit_var = tk.StringVar(value=self._reg(None, "speed_unlimited", "Без обмежень"))
        ttk.Combobox(opts_row, textvariable=self.speed_limit_var,
                     values=list(SPEED_PRESETS.keys()), state="readonly", width=16
                     ).pack(side="left", padx=10)

        self.send_btn = ModernButton(f, text=self._reg(None, "enqueue_btn", "📤  Додати в чергу"),
                                     variant="accent", command=self._enqueue)
        self.send_btn.pack(pady=16)
        self._reg(self.send_btn, "enqueue_btn")

        prog_frame = ttk.Frame(f)
        prog_frame.pack(fill="x", padx=16, pady=(0, 16))
        self.progress_var = tk.DoubleVar()
        self.progress_bar = RoundedProgressBar(prog_frame, height=10)
        self.progress_bar.pack(fill="x", pady=(0, 6))
        self.checksum_var = tk.StringVar()
        ttk.Label(prog_frame, textvariable=self.checksum_var,
                 font=("Consolas", 9)).pack(anchor="w")

    # ── Queue tab ────────────────────────────────────────────────────────────

    def _build_queue_tab(self, pad):
        f = self._tab_queue

        cols = {
            "id": (self._reg(None, "col_id", "ID"), 60, "center"),
            "file": (self._reg(None, "col_file", "Файл"), 240, "w"),
            "status": (self._reg(None, "col_status", "Статус"), 90, "center"),
            "progress": (self._reg(None, "col_progress", "Прогрес"), 120, "w"),
            "speed": (self._reg(None, "col_speed", "Швидкість"), 90, "center"),
        }
        self.queue_tree = ttk.Treeview(f, columns=list(cols.keys()), show="headings", height=12)
        for cid, (label, width, anchor) in cols.items():
            self.queue_tree.heading(cid, text=label)
            self._reg(self.queue_tree, f"col_{cid}", attr="column_heading", args=(cid,))
            self.queue_tree.column(cid, width=width, anchor=anchor)

        # Color tags synchronized with our palette
        p = get_palette()
        self.queue_tree.tag_configure("done",      background="", foreground=p["green"])
        self.queue_tree.tag_configure("error",     background="", foreground=p["red"])
        self.queue_tree.tag_configure("sending",   background="", foreground=p["accent"])
        self.queue_tree.tag_configure("cancelled", background="", foreground=p["fg_dim"])
        self.queue_tree.tag_configure("pending",   background="", foreground="")

        sb = ttk.Scrollbar(f, orient="vertical", command=self.queue_tree.yview)
        self.queue_tree.configure(yscrollcommand=sb.set)
        self.queue_tree.pack(side="left", fill="both", expand=True, padx=(16, 0), pady=16)
        sb.pack(side="left", fill="y", pady=16)

        btn_col = ttk.Frame(f)
        btn_col.pack(side="left", padx=16, pady=16, anchor="n")
        self.pause_btn = ModernButton(btn_col, text=self._reg(None, "pause", "⏸  Пауза"),     width=14, command=self._queue_pause)
        self.pause_btn.pack(pady=4, fill="x")
        self._reg(self.pause_btn, "pause")
        
        self.resume_btn = ModernButton(btn_col, text=self._reg(None, "resume", "▶  Продовжити"), width=14, command=self._queue_resume)
        self.resume_btn.pack(pady=4, fill="x")
        self._reg(self.resume_btn, "resume")
        
        self.cancel_btn = ModernButton(btn_col, text=self._reg(None, "cancel", "✖  Скасувати"),  width=14, variant="danger",
                     command=self._queue_cancel)
        self.cancel_btn.pack(pady=4, fill="x")
        self._reg(self.cancel_btn, "cancel")
        
        ttk.Separator(btn_col, orient="horizontal").pack(fill="x", pady=12)
        
        self.clear_q_btn = ModernButton(btn_col, text=self._reg(None, "clear", "🗑  Очистити"),  width=14,
                     command=self._queue_clear)
        self.clear_q_btn.pack(fill="x")
        self._reg(self.clear_q_btn, "clear")

    # ── History tab ──────────────────────────────────────────────────────────

    def _build_history_tab(self, pad):
        f = self._tab_history

        cols = {
            "time": (self._reg(None, "col_time", "Час"), 140),
            "direction": (self._reg(None, "col_direction", "Напрям"), 70, "center"),
            "file": (self._reg(None, "col_file", "Файл"), 280),
            "status": (self._reg(None, "col_status", "Статус"), 90, "center"),
            "checksum": (self._reg(None, "col_checksum", "SHA256"), 120),
        }
        self.hist_tree = ttk.Treeview(f, columns=list(cols.keys()), show="headings", height=14)
        for cid, (label, width, *anchor) in cols.items():
            self.hist_tree.heading(cid, text=label)
            self._reg(self.hist_tree, f"col_{cid}", attr="column_heading", args=(cid,))
            self.hist_tree.column(cid, width=width, anchor=anchor[0] if anchor else "w")

        sb = ttk.Scrollbar(f, orient="vertical", command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=sb.set)
        self.hist_tree.pack(side="left", fill="both", expand=True, padx=(16, 0), pady=16)
        
        # Color tags synchronized with our palette
        p = get_palette()
        self.hist_tree.tag_configure("done", foreground=p["green"])
        self.hist_tree.tag_configure("error", foreground=p["red"])
        self.hist_tree.tag_configure("info", foreground=p["accent"])

        sb.pack(side="left", fill="y", pady=16)

        btn_col = ttk.Frame(f)
        btn_col.pack(side="left", padx=16, pady=16, anchor="n")
        self.hist_refresh_btn = ModernButton(btn_col, text=self._reg(None, "refresh", "🔄  Оновити"), width=14,
                     command=self._reload_history)
        self.hist_refresh_btn.pack(pady=4, fill="x")
        self._reg(self.hist_refresh_btn, "refresh")
        
        self.hist_clear_btn = ModernButton(btn_col, text=self._reg(None, "clear", "🗑  Очистити"), width=14, variant="danger",
                     command=self._clear_history)
        self.hist_clear_btn.pack(pady=4, fill="x")
        self._reg(self.hist_clear_btn, "clear")

        self._reload_history()

    # ── Host actions ─────────────────────────────────────────────────────────

    def _toggle_hosting(self):
        if self.is_hosting:
            self.manager.stop_hosting()
            self._update_host_tab_ui(active=False)
            self._save_settings()
        else:
            try:
                port = int(self.port_var.get())
                if not (1 <= port <= 65535):
                    raise ValueError
            except ValueError:
                themed_showerror(self.root, t("error", "Помилка"), t("error_invalid_port", "Невірний порт (1–65535)."))
                return
            save_dir = self.save_dir_var.get().strip()
            if not save_dir:
                themed_showerror(self.root, t("error", "Помилка"), t("error_no_save_dir", "Вкажіть папку для збереження файлів."))
                return
            self.manager.start_hosting(
                port=port,
                save_dir=save_dir,
                progress_cb=self._on_recv_progress,
                status_cb=self._on_host_status,
                psk=self.psk_var.get(),
            )
            self.is_hosting = True
            self._update_host_tab_ui(active=True, port=port)
            self._save_settings()

    def _update_host_tab_ui(self, active: bool, port: int = 0):
        """Helper to switch 'Host' button and status styles."""
        p = get_palette()
        if active:
            self.host_btn.config(text=t("stop_hosting", "⏹  Зупинити прийом"))
            self.host_btn._variant = "danger"
            self.host_btn._bg = p["btn_danger_bg"]
            self.host_btn._hover = p["btn_danger_hover"]
            self.host_btn.configure(bg=p["btn_danger_bg"], fg=p["btn_danger_fg"])
            self.host_status_var.set(t("waiting_on_port", "Очікування на порту {port}...").format(port=port))
        else:
            self.host_btn.config(text=t("start_hosting", "▶  Почати прийом"))
            self.host_btn._variant = "accent"
            self.host_btn._bg = p["btn_accent_bg"]
            self.host_btn._hover = p["btn_accent_hover"]
            self.host_btn.configure(bg=p["btn_accent_bg"], fg=p["btn_accent_fg"])
            self.host_status_var.set(t("host_not_active", "Не активний"))

    def _choose_save_dir(self):
        d = filedialog.askdirectory(initialdir=self.save_dir_var.get())
        if d:
            self.save_dir_var.set(d)

    def _open_firewall(self):
        self.status_var.set("Додаємо правило брандмауера...")
        threading.Thread(target=self._do_firewall, daemon=True).start()

    def _do_firewall(self):
        ok, msg = add_firewall_rule()
        self.root.after(0, lambda: self.status_var.set(msg))
        if not ok:
            self.root.after(0, lambda: themed_showwarning(
                self.root,
                "Брандмауер",
                f"{msg}\n\nВідкрийте вручну:\nПанель керування → Брандмауер Windows → "
                "Дозволити програму через брандмауер",
            ))

    # ── Send actions ─────────────────────────────────────────────────────────

    def _discover(self):
        try:
            port = int(self.send_port_var.get())
        except ValueError:
            themed_showerror(self.root, t("error", "Помилка"), t("error_invalid_port", "Невірний порт (1–65535)."))
            return
        self.manager.discover_hosts(port, timeout=2.0, done_cb=self._on_discover_done)
        self.status_var.set(t("status_scanning", "Пошук хостів..."))

    def _on_discover_done(self, hosts: list[dict]):
        def _update():
            self._disc_hosts = hosts
            self.disc_listbox.delete(0, "end")
            if not hosts:
                self.status_var.set(t("status_no_hosts", "Хостів не знайдено."))
                return
            for h in hosts:
                self.disc_listbox.insert("end", f"{h['hostname']}  ({h['ip']}:{h['port']})")
            self.status_var.set(t("status_hosts_found", "Знайдено {count} хост(ів).").format(count=len(hosts)))
        self.root.after(0, _update)

    def _on_disc_select(self, _event=None):
        sel = self.disc_listbox.curselection()
        if not sel:
            return
        h = self._disc_hosts[sel[0]]
        self.target_ip_var.set(h["ip"])
        self.send_port_var.set(str(h["port"]))

    def _add_files(self):
        for p in filedialog.askopenfilenames():
            self._add_path(p)

    def _add_folder(self):
        d = filedialog.askdirectory()
        if d:
            self._add_path(d)

    def _add_path(self, path: str) -> None:
        if path and path not in self._queue_file_paths:
            self._queue_file_paths.append(path)
            self.files_listbox.insert("end", path)

    def _remove_selected_file(self):
        for i in reversed(self.files_listbox.curselection()):
            self.files_listbox.delete(i)
            self._queue_file_paths.pop(i)

    def _on_drop(self, event) -> None:
        """Handle drag & drop onto the files listbox."""
        try:
            for path in _parse_dnd_data(event.data):
                self._add_path(path)
        except Exception:
            pass
        # Reset DnD highlight
        if hasattr(self, '_files_frame'):
            self._files_frame.configure(relief="groove")

    def _enqueue(self):
        host = self.target_ip_var.get().strip()
        if not host:
            themed_showerror(self.root, t("error", "Помилка"), t("error_no_host", "Введіть IP хоста."))
            return
        if not self._queue_file_paths:
            themed_showerror(self.root, t("error", "Помилка"), t("error_no_files", "Додайте файли або папки."))
            return
        try:
            port = int(self.send_port_var.get())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            themed_showerror(self.root, t("error", "Помилка"), t("error_invalid_port", "Невірний порт (1–65535)."))
            return

        speed_limit = SPEED_PRESETS.get(self.speed_limit_var.get(), 0)
        connect_timeout = float(self.settings.get("connect_timeout", 30))
        ids = self.manager.enqueue(
            host=host,
            port=port,
            paths=list(self._queue_file_paths),
            speed_limit_bps=speed_limit,
            psk=self.psk_var.get(),
            connect_timeout=connect_timeout,
            overwrite_cb=self._overwrite_dialog,
        )
        for job_id, path in zip(ids, self._queue_file_paths):
            self.queue_tree.insert("", "end", iid=job_id, tags=("pending",), values=(
                job_id, os.path.basename(path), "⏳ pending", "0%", "",
            ))

        self.files_listbox.delete(0, "end")
        self._queue_file_paths.clear()
        self.status_var.set(f"Додано {len(ids)} завдань у чергу.")

    # ── Queue actions ─────────────────────────────────────────────────────────

    def _selected_job_id(self) -> str | None:
        sel = self.queue_tree.selection()
        return sel[0] if sel else None

    def _queue_pause(self):
        jid = self._selected_job_id()
        if jid:
            self.manager.pause_job(jid)

    def _queue_resume(self):
        jid = self._selected_job_id()
        if jid:
            self.manager.resume_job(jid)

    def _queue_cancel(self):
        jid = self._selected_job_id()
        if jid:
            self.manager.cancel_job(jid)

    def _queue_clear(self):
        self.manager.clear_done_jobs()
        active = {"⏳ pending", "📤 sending"}
        for iid in self.queue_tree.get_children():
            if self.queue_tree.item(iid, "values")[2] not in active:
                self.queue_tree.delete(iid)

    def _progress_indeterminate(self):
        """Switch progress bar to bouncing animation (connecting state)."""
        self.progress_bar.start_indeterminate()
        self._set_status_dot("sending")

    def _progress_determinate(self, value: float = 0):
        """Switch progress bar back to normal percentage mode."""
        self.progress_bar.stop_indeterminate()
        self.progress_bar.set(value)
        self.progress_var.set(value)

    def _set_status_dot(self, state: str) -> None:
        """Update status bar indicator dot color."""
        p = get_palette()
        colors = {
            "idle":     p.get("green",  "#a6e3a1"),
            "sending":  p.get("accent", "#89b4fa"),
            "error":    p.get("red",    "#f38ba8"),
            "done":     p.get("green",  "#a6e3a1"),
        }
        self._status_dot.configure(fg=colors.get(state, p.get("fg_dim", "#6c7086")))

    # ── History actions ───────────────────────────────────────────────────────

    def _reload_history(self):
        self.hist_tree.delete(*self.hist_tree.get_children())
        for entry in reversed(load_history()):
            chk = entry.get("checksum", "")
            short_chk = chk[:12] + "…" if len(chk) > 12 else chk
            tag = entry.get("status", "info")
            self.hist_tree.insert("", "end", values=(
                entry.get("time", ""),
                entry.get("direction", ""),
                entry.get("file", ""),
                entry.get("status", ""),
                short_chk,
            ), tags=(tag,))

    def _clear_history(self):
        title = t("clear_history_title", "Очистити")
        msg = t("clear_history_msg", "Видалити всю історію?")
        if themed_ask_yesno(self.root, title, msg):
            clear_history()
            self._reload_history()

    # ── Overwrite dialog ──────────────────────────────────────────────────────

    def _overwrite_dialog(self, filename: str) -> str:
        """Show overwrite dialog from the main thread. Returns 'overwrite'|'skip'|'rename'."""
        result: list[str] = ["rename"]
        done = threading.Event()

        def _ask():
            title = t("file_exists_title", "Файл існує")
            msg = t("file_exists_msg", "Файл «{filename}» вже існує.\n\nТак = перезаписати\nНі = перейменувати\nСкасувати = пропустити").format(filename=filename)
            d = themed_askyesnocancel(self.root, title, msg)
            if d is True:
                result[0] = "overwrite"
            elif d is False:
                result[0] = "rename"
            else:
                result[0] = "skip"
            done.set()

        self.root.after(0, _ask)
        done.wait(timeout=30)
        _log.info("Overwrite dialog for %s: %s", filename, result[0])
        return result[0]

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_job_update(self, job: QueueJob):
        with self._ui_update_lock:
            self._ui_update_queue[f"job:{job.job_id}"] = {
                "type": "job",
                "obj": job,
                "status": job.status,
                "percent": job.progress.percent,
                "speed": job.progress.speed_bps,
            }

    def _on_recv_progress(self, prog: TransferProgress):
        with self._ui_update_lock:
            self._ui_update_queue["recv"] = {
                "type": "recv",
                "obj": prog,
                "percent": prog.percent,
                "speed": prog.speed_bps,
            }

    def _on_host_status(self, status: str):
        # Host status is usually rare, update immediately
        self.root.after(0, lambda: on_host_status(self, status))

    # ── Notifications ─────────────────────────────────────────────────────────

    # _notify_done is handled by ui.callbacks._notify_done (called via on_job_update / on_host_status)

    # ── Tray / window ─────────────────────────────────────────────────────────

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _quit(self) -> None:
        self.manager.stop()
        self._tray.stop()
        self.root.destroy()

    def _restart_app(self) -> None:
        """Restart the application (for language change etc.)."""
        import sys, os
        self.manager.stop()
        self._tray.stop()
        self.root.destroy()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _open_settings(self):
        SettingsDialog(self.root, on_save=self._apply_settings)

    def _apply_settings(self, data: dict):
        """Apply saved settings to the running UI."""
        self.settings = data
        reconfigure(data.get("log_level", "INFO"))
        self.port_var.set(str(data.get("port", 5001)))
        self.send_port_var.set(str(data.get("port", 5001)))
        self.save_dir_var.set(data.get("save_dir", ""))
        # PSK: prefer keyring
        from services.keyring_service import load_psk as _lp
        psk = _lp() or data.get("psk", "")
        self.psk_var.set(psk)
        # Re-apply theme if changed
        new_theme = data.get("theme", "dark")
        if new_theme != self._theme_mode:
            self._theme_mode = new_theme
            apply_theme(self.root, new_theme)
        # Language change
        new_lang = data.get("language", "ua")
        from services.i18n_service import get_lang, init_i18n
        if new_lang != get_lang():
            init_i18n(new_lang)
            self._retranslate_ui()
        
        self.status_var.set(t("settings_saved", "Налаштування збережено."))

    def _check_firewall(self):
        def _check():
            if not check_rule_exists():
                self.root.after(500, lambda: self.status_var.set(
                    t("firewall_hint", "Порада: натисніть 'Відкрити доступ у мережі' для налаштування брандмауера.")
                ))
        threading.Thread(target=_check, daemon=True).start()

    def _save_settings(self):
        try:
            self.settings["port"] = int(self.port_var.get())
        except ValueError:
            pass
        self.settings["save_dir"] = self.save_dir_var.get()
        self.settings["psk"] = self.psk_var.get()
        save_settings(self.settings)

    def _toggle_theme(self):
        new_mode = "light" if self._theme_mode == "dark" else "dark"
        self._theme_mode = new_mode
        apply_theme(self.root, new_mode)
        # Update custom widgets manually
        for child in self.root.winfo_children():
            self._update_recursive(child)
        self.settings["theme"] = new_mode
        save_settings(self.settings)

    def _schedule_ui_update(self):
        """Schedule the next batch of UI updates."""
        # Increase interval to 200ms (5 FPS) for better dragging performance
        self.root.after(200, self._apply_ui_updates)

    def _apply_ui_updates(self):
        """Apply all queued UI updates at once to reduce jitter and redraws."""
        updates = {}
        with self._ui_update_lock:
            if self._ui_update_queue:
                updates = self._ui_update_queue.copy()
                self._ui_update_queue.clear()
        
        if updates:
            from ui.callbacks import apply_batched_updates
            apply_batched_updates(self, updates)
            
        if not getattr(self, '_quitting', False):
            self._schedule_ui_update()

    def _update_recursive(self, widget):
        if hasattr(widget, "update_theme"):
            widget.update_theme()
        for child in widget.winfo_children():
            self._update_recursive(child)

    def run(self):
        self.root.mainloop()
        self.manager.stop()
        self._tray.stop()
