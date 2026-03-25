"""Settings dialog window."""
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Callable

from config.settings import load_settings, save_settings
from services.keyring_service import keyring_available, save_psk, load_psk
from services.i18n_service import t, init_i18n
from ui.widgets import ModernButton, themed_showerror, themed_ask_yesno

_THEMES = ["dark", "light"]
_OVERWRITE_OPTIONS = ["ask", "overwrite", "skip", "rename"]
_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, on_save: Callable[[dict], None] | None = None):
        super().__init__(parent)
        self.title(t("settings_title", "Налаштування"))
        self.resizable(False, False)
        self.grab_set()  # modal
        self.transient(parent)

        self._on_save = on_save
        self._settings = load_settings()
        self._vars: dict[str, tk.Variable] = {}

        self._build()
        self._center(parent)

    # ── Build ────────────────────────────────────────────────────────────────

    def _build(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 0))

        tab_net  = tk.Frame(nb)
        tab_app  = tk.Frame(nb)
        tab_sec  = tk.Frame(nb)

        nb.add(tab_net, text=t("tab_network", "  🌐 Мережа  "))
        nb.add(tab_app, text=t("tab_app", "  🖥 Додаток  "))
        nb.add(tab_sec, text=t("tab_security", "  🔒 Безпека  "))

        self._build_network(tab_net)
        self._build_app(tab_app)
        self._build_security(tab_sec)

        # Buttons
        btn_row = tk.Frame(self)
        btn_row.pack(fill="x", padx=10, pady=8)
        ModernButton(btn_row, text=t("save_btn", "Зберегти"), variant="accent",
                     width=12, command=self._save).pack(side="right", padx=4)
        ModernButton(btn_row, text=t("cancel_btn", "Скасувати"), width=12,
                     command=self.destroy).pack(side="right")
        ModernButton(btn_row, text=t("reset_btn", "Скинути"), width=12,
                     command=self._reset).pack(side="left")

    def _build_network(self, f: tk.Frame):
        pad = {"padx": 12, "pady": 5}

        self._row(f, t("port_tcp", "Порт TCP:"), "port",
                  str(self._settings.get("port", 5001)), **pad)

        self._row(f, t("port_discovery", "Порт Discovery (UDP):"), "discovery_port",
                  str(self._settings.get("discovery_port", 5002)), **pad)

        # Save directory
        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text=t("save_dir_label", "Папка збереження:"), width=22, anchor="w").pack(side="left")
        v = tk.StringVar(value=self._settings.get("save_dir", ""))
        self._vars["save_dir"] = v
        tk.Entry(row, textvariable=v, width=26).pack(side="left", padx=4)
        tk.Button(row, text="...",
                  command=lambda: v.set(filedialog.askdirectory() or v.get())
                  ).pack(side="left")

        self._row(f, t("connect_timeout_label", "Таймаут з'єднання (сек):"), "connect_timeout",
                  str(self._settings.get("connect_timeout", 30)), **pad)

    def _build_app(self, f: tk.Frame):
        pad = {"padx": 12, "pady": 5}

        # Notifications
        self._check(f, t("sound_notify", "Звукові сповіщення"), "sound_notify",
                    self._settings.get("sound_notify", True), **pad)
        self._check(f, t("toast_notify", "Toast-сповіщення"), "toast_notify",
                    self._settings.get("toast_notify", True), **pad)
        self._check(f, t("minimize_to_tray", "Згортати у трей при закритті"), "minimize_to_tray",
                    self._settings.get("minimize_to_tray", True), **pad)
        self._check(f, t("autostart_host", "Запускати прийом при старті"), "autostart_host",
                    self._settings.get("autostart_host", False), **pad)

        # Max history
        self._row(f, t("max_history_label", "Макс. записів в історії:"), "max_history",
                  str(self._settings.get("max_history", 200)), **pad)

        # Parallel transfers
        self._row(f, t("parallel_transfers_label", "Паралельних трансферів:"), "max_parallel_transfers",
                  str(self._settings.get("max_parallel_transfers", 3)), **pad)
    def _build_app(self, f: tk.Frame):
        pad = {"padx": 12, "pady": 5}

        # Notifications
        self._check(f, t("sound_notify", "Звукові сповіщення"), "sound_notify",
                    self._settings.get("sound_notify", True), **pad)
        self._check(f, t("toast_notify", "Toast-сповіщення"), "toast_notify",
                    self._settings.get("toast_notify", True), **pad)
        self._check(f, t("minimize_to_tray", "Згортати у трей при закритті"), "minimize_to_tray",
                    self._settings.get("minimize_to_tray", True), **pad)
        self._check(f, t("autostart_host", "Запускати прийом при старті"), "autostart_host",
                    self._settings.get("autostart_host", False), **pad)

        # Max history
        self._row(f, t("max_history_label", "Макс. записів в історії:"), "max_history",
                  str(self._settings.get("max_history", 200)), **pad)

        # Parallel transfers
        self._row(f, t("parallel_transfers_label", "Паралельних трансферів:"), "max_parallel_transfers",
                  str(self._settings.get("max_parallel_transfers", 3)), **pad)
        tk.Label(f, text=t("help_recomm", "Рекомендовано: 1–5"), fg="gray",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=12)

        # Log level
        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text=t("log_level_label", "Рівень логування:"), width=26, anchor="w").pack(side="left")
        v = tk.StringVar(value=self._settings.get("log_level", "INFO"))
        self._vars["log_level"] = v
        ttk.Combobox(row, textvariable=v, values=_LOG_LEVELS,
                     state="readonly", width=10).pack(side="left", padx=4)

        # Theme
        row2 = tk.Frame(f)
        row2.pack(fill="x", **pad)
        tk.Label(row2, text=t("theme_label", "Тема:"), width=26, anchor="w").pack(side="left")
        v2 = tk.StringVar(value=self._settings.get("theme", "dark"))
        self._vars["theme"] = v2
        ttk.Combobox(row2, textvariable=v2, values=_THEMES,
                     state="readonly", width=10).pack(side="left", padx=4)

        # Language
        row3 = tk.Frame(f)
        row3.pack(fill="x", **pad)
        tk.Label(row3, text=t("language", "Мова:"), width=26, anchor="w").pack(side="left")
        v3 = tk.StringVar(value=self._settings.get("language", "ua"))
        self._vars["language"] = v3
        ttk.Combobox(row3, textvariable=v3, values=["ua", "en"],
                     state="readonly", width=10).pack(side="left", padx=4)

    def _build_security(self, f: tk.Frame):
        pad = {"padx": 12, "pady": 5}

        # PSK with keyring support
        row = tk.Frame(f)
        row.pack(fill="x", **pad)
        tk.Label(row, text=t("psk_label", "PSK (ключ шифрування):"), width=24, anchor="w").pack(side="left")

        # Load PSK: prefer keyring, fallback to settings
        psk_val = load_psk() or self._settings.get("psk", "")
        v = tk.StringVar(value=psk_val)
        self._vars["psk"] = v
        psk_e = tk.Entry(row, textvariable=v, width=22, show="*")
        psk_e.pack(side="left", padx=4)
        show_v = tk.BooleanVar()
        tk.Checkbutton(row, text="👁", variable=show_v,
                       command=lambda: psk_e.config(show="" if show_v.get() else "*")
                       ).pack(side="left")

        if keyring_available():
            tk.Label(f, text=t("psk_hint_secure", "🔑 PSK зберігається в OS Keyring (безпечно)."),
                     fg="green", font=("Segoe UI", 8)).pack(anchor="w", padx=12)
        else:
            tk.Label(f,
                     text=t("psk_hint_warn", "⚠ keyring не встановлено — PSK зберігається у plaintext!"),
                     fg="orange", font=("Segoe UI", 8), justify="left",
                     ).pack(anchor="w", padx=12)

        tk.Label(f, text=t("psk_hint_off", "Залиште порожнім щоб вимкнути шифрування."),
                 fg="gray", font=("Segoe UI", 8)).pack(anchor="w", padx=12)

        self._row(f, t("chunk_size_label", "Розмір чанку (байт):"), "chunk_size",
                  str(self._settings.get("chunk_size", 65536)), **pad)
        tk.Label(f, text=t("help_chunk", "Рекомендовано: 32768 – 131072"),
                 fg="gray", font=("Segoe UI", 8)).pack(anchor="w", padx=12)

        # File size limit
        self._row(f, t("max_file_size_label", "Макс. розмір файлу (МБ):"), "max_file_size_mb",
                  str(self._settings.get("max_file_size_mb", 0)), **pad)
        tk.Label(f, text=t("help_mb", "0 = без обмежень"), fg="gray",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=12)

        # Overwrite policy
        row2 = tk.Frame(f)
        row2.pack(fill="x", **pad)
        tk.Label(row2, text=t("overwrite_policy_label", "При перезапису файлу:"), width=24, anchor="w").pack(side="left")
        v2 = tk.StringVar(value=self._settings.get("overwrite_existing", "ask"))
        self._vars["overwrite_existing"] = v2
        ttk.Combobox(row2, textvariable=v2, values=_OVERWRITE_OPTIONS,
                     state="readonly", width=12).pack(side="left", padx=4)
        
        hint_text = "\n".join([
            t("overwrite_ask"), t("overwrite_all"), t("overwrite_skip"), t("overwrite_rename")
        ])
        tk.Label(f, text=hint_text,
                 fg="gray", font=("Segoe UI", 8), wraplength=340, justify="left",
                 ).pack(anchor="w", padx=12)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _row(self, parent, label: str, key: str, default: str, **pack_kw):
        row = tk.Frame(parent)
        row.pack(fill="x", **pack_kw)
        tk.Label(row, text=label, width=26, anchor="w").pack(side="left")
        v = tk.StringVar(value=default)
        self._vars[key] = v
        tk.Entry(row, textvariable=v, width=14).pack(side="left", padx=4)

    def _check(self, parent, label: str, key: str, default: bool, **pack_kw):
        v = tk.BooleanVar(value=default)
        self._vars[key] = v
        tk.Checkbutton(parent, text=label, variable=v).pack(anchor="w", **pack_kw)

    def _center(self, parent: tk.Tk):
        self.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width() // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px - w // 2}+{py - h // 2}")

    # ── Actions ──────────────────────────────────────────────────────────────

    def _collect(self) -> dict:
        result = dict(self._settings)
        for key, var in self._vars.items():
            val = var.get()
            # coerce numeric strings (including negative)
            if isinstance(val, str):
                stripped = val.strip()
                try:
                    val = int(stripped)
                except ValueError:
                    val = stripped
            result[key] = val
        return result

    def _save(self):
        data = self._collect()
        # Валідація числових полів
        for f in ("connect_timeout", "chunk_size", "max_history", "max_parallel_transfers"):
            v = data.get(f)
            if not isinstance(v, int) or v <= 0:
                themed_showerror(self, t("error", "Помилка"), f"{t('error_invalid_value', 'Невірне значення')} '{f}'.")
                return
        for f in ("port", "discovery_port"):
            v = data.get(f)
            if not isinstance(v, int) or not (1 <= v <= 65535):
                themed_showerror(self, t("error", "Помилка"), f"{t('error_invalid_port', 'Невірний порт')} '{f}'.")
                return
        max_mb = data.get("max_file_size_mb", 0)
        if not isinstance(max_mb, int) or max_mb < 0:
            themed_showerror(self, t("error", "Помилка"), t("error_invalid_size", "Макс. розмір файлу має бути >= 0."))
            return

        # Save PSK to keyring (remove from settings dict if keyring available)
        psk = data.get("psk", "")
        init_i18n(data.get("language", "ua"))
        if keyring_available():
            save_psk(psk)
            data.pop("psk", None)  # don't store in plaintext

        save_settings(data)
        if self._on_save:
            self._on_save(data)
        self.destroy()

    def _reset(self):
        if themed_ask_yesno(self, t("reset_btn", "Скинути"), t("reset_confirm", "Скинути всі налаштування до стандартних?")):
            defaults = {
                "port": 5001,
                "discovery_port": 5002,
                "connect_timeout": 30,
                "chunk_size": 65536,
                "max_history": 200,
                "max_parallel_transfers": 3,
                "max_file_size_mb": 0,
                "overwrite_existing": "ask",
                "log_level": "INFO",
                "sound_notify": True,
                "toast_notify": True,
                "minimize_to_tray": True,
                "autostart_host": False,
                "psk": "",
            }
            for key, var in self._vars.items():
                if key in defaults:
                    var.set(defaults[key])
