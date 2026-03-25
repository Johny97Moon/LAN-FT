"""
UI callback handlers — separated from MainWindow layout code.
Each function receives the window instance as first argument to update UI state.
"""
import os

from services.history_service import append_history
from services.i18n_service import t
from services.notification_service import play_sound
from ui.constants import STATUS_ICONS, fmt_speed
from ui.toast import show_toast as in_app_toast


def on_job_update(win, job) -> None:
    """Handle queue job status changes — update treeview, progress bar, history."""
    def _update():
        icon  = STATUS_ICONS.get(job.status, "")
        pct   = f"{job.progress.percent:.0f}%"
        spd   = fmt_speed(job.progress.speed_bps)
        label = f"{icon} {job.status}"

        if win.queue_tree.exists(job.job_id):
            fname = win.queue_tree.item(job.job_id, "values")[1]
            win.queue_tree.item(job.job_id, tags=(job.status,),
                                values=(job.job_id, fname, label, pct, spd))

        if job.status == "sending":
            # Switch to indeterminate while connecting (0%), determinate once data flows
            if job.progress.percent == 0:
                if hasattr(win, '_progress_indeterminate'):
                    win._progress_indeterminate()
            else:
                if hasattr(win, '_progress_determinate'):
                    win._progress_determinate(job.progress.percent)
                else:
                    win.progress_var.set(job.progress.percent)
            win.speed_var.set(spd)
            win.status_var.set(f"{t('sending_prefix', 'Надсилання')} {job.job_id}: {pct}")

        elif job.status == "done":
            if hasattr(win, '_progress_determinate'):
                win._progress_determinate(100)
            else:
                win.progress_var.set(100)
            win.speed_var.set("")
            if job.progress.checksum:
                win.checksum_var.set(f"SHA256: {job.progress.checksum}")
            win.status_var.set(f"✔ {job.job_id} — {t('ready_done', 'готово')}")
            if hasattr(win, '_set_status_dot'):
                win._set_status_dot("done")
            fname = (
                win.queue_tree.item(job.job_id, "values")[1]
                if win.queue_tree.exists(job.job_id)
                else job.job_id
            )
            _notify_done(win, f"{t('sent_direction', 'надіслано').replace('→ ', '')}: {fname}")
            append_history({
                "direction": t("sent_direction", "→ надіслано"),
                "file": fname,
                "status": "done",
                "checksum": job.progress.checksum,
            })
            win._reload_history()

        elif job.status == "error":
            win.status_var.set(f"✘ {job.job_id}: {job.progress.error}")
            if hasattr(win, '_set_status_dot'):
                win._set_status_dot("error")
            if hasattr(win, '_progress_determinate'):
                win._progress_determinate(0)
            play_sound(success=False)

        elif job.status == "cancelled":
            win.status_var.set(f"✖ {job.job_id} {t('cancelled_suffix', 'скасовано')}")

    win.root.after(0, _update)


def on_recv_progress(win, prog) -> None:
    """Update progress bar during file reception."""
    def _update():
        if hasattr(win.progress_bar, 'set'):
            win.progress_bar.set(prog.percent)
        win.progress_var.set(prog.percent)
        win.speed_var.set(fmt_speed(prog.speed_bps))
        win.status_var.set(f"{t('receiving_prefix', 'Отримання:')} {prog.percent:.1f}%")
    win.root.after(0, _update)


def on_host_status(win, status: str) -> None:
    """Handle receiver status changes — update host tab labels."""
    def _update():
        if status == "listening":
            win.host_status_var.set(t("waiting_on_port", "Очікування на порту {port}...").format(port=win.port_var.get()))
        elif status.startswith("connected:"):
            addr = status.split(':', 1)[1]
            win.host_status_var.set(t("connection_from", "З'єднання від {addr}").format(addr=addr))
        elif status.startswith("done:"):
            path = status.split(":", 1)[1]
            fname = os.path.basename(path) or path
            win.host_status_var.set(f"{t('received_prefix', 'Отримано:')} {path}")
            if hasattr(win.progress_bar, 'set'):
                win.progress_bar.set(100)
            win.progress_var.set(100)
            _notify_done(win, f"{t('received_prefix', 'Отримано:')} {fname}")
            append_history({
                "direction": t("received_direction", "← отримано"),
                "file": fname,
                "status": "done",
                "checksum": "",
            })
            win._reload_history()
        elif status.startswith("error:checksum_mismatch:"):
            path = status.split(":", 2)[2]
            win.host_status_var.set(t("checksum_error", "Помилка цілісності"))
            play_sound(success=False)
            from ui.widgets import themed_showerror
            themed_showerror(win.root, t("error", "Помилка"), f"{t('checksum_mismatch', 'Контрольна сума не збіглася:')}\n{path}")
        elif status.startswith("error:"):
            msg = status.split(':', 1)[1]
            win.host_status_var.set(f"{t('error', 'Помилка')}: {msg}")
            play_sound(success=False)

    win.root.after(0, _update)


def apply_batched_updates(win, updates: dict) -> None:
    """Apply a dictionary of queued updates to the UI in one go."""
    # Handle receive progress (global bar)
    if "recv" in updates:
        u = updates["recv"]
        prog = u["obj"]
        if hasattr(win.progress_bar, 'set'):
            win.progress_bar.set(u["percent"])
        win.progress_var.set(u["percent"])
        win.speed_var.set(fmt_speed(u["speed"]))
        win.status_var.set(f"{t('receiving_prefix', 'Отримання:')} {u['percent']:.1f}%")

    need_history_reload = False

    # Handle individual queue jobs
    for key, u in updates.items():
        if not key.startswith("job:"):
            continue
        
        job = u["obj"]
        icon  = STATUS_ICONS.get(u["status"], "")
        pct_val = u["percent"]
        pct_str = f"{pct_val:.0f}%"
        spd_str = fmt_speed(u["speed"])
        label = f"{icon} {u['status']}"

        if win.queue_tree.exists(job.job_id):
            # Optimization: use Python-side cache to avoid expensive win.queue_tree.item (GET) calls
            new_state = (label, pct_str, spd_str)
            if win._ui_cache.get(job.job_id) != new_state:
                fname = win.queue_tree.item(job.job_id, "values")[1]
                win.queue_tree.item(job.job_id, tags=(u["status"],),
                                    values=(job.job_id, fname, label, pct_str, spd_str))
                win._ui_cache[job.job_id] = new_state

        if u["status"] == "sending":
            if pct_val == 0:
                if hasattr(win, '_progress_indeterminate'):
                    win._progress_indeterminate()
            else:
                if hasattr(win, '_progress_determinate'):
                    win._progress_determinate(pct_val)
                else:
                    win.progress_var.set(pct_val)
            win.speed_var.set(spd_str)
            # Only update global status label if it changed significantly
            status_text = f"{t('sending_prefix', 'Надсилання')} {job.job_id}: {pct_str}"
            if getattr(win, '_last_status_text', '') != status_text:
                win.status_var.set(status_text)
                win._last_status_text = status_text
        
        elif u["status"] == "done":
            if hasattr(win, '_progress_determinate'):
                win._progress_determinate(100)
            else:
                win.progress_var.set(100)
            win.speed_var.set("")
            if job.progress.checksum:
                win.checksum_var.set(f"SHA256: {job.progress.checksum}")
            win.status_var.set(f"✔ {job.job_id} — {t('ready_done', 'готово')}")
            if hasattr(win, '_set_status_dot'):
                win._set_status_dot("done")
            fname = (
                win.queue_tree.item(job.job_id, "values")[1]
                if win.queue_tree.exists(job.job_id)
                else job.job_id
            )
            _notify_done(win, f"{t('sent_direction', 'надіслано').replace('→ ', '')}: {fname}")
            append_history({
                "direction": t("sent_direction", "→ надіслано"),
                "file": fname,
                "status": "done",
                "checksum": job.progress.checksum,
            })
            need_history_reload = True

        elif u["status"] == "error":
            win.status_var.set(f"✘ {job.job_id}: {job.progress.error}")
            if hasattr(win, '_set_status_dot'):
                win._set_status_dot("error")
            if hasattr(win, '_progress_determinate'):
                win._progress_determinate(0)
            play_sound(success=False)

        elif u["status"] == "cancelled":
            win.status_var.set(f"✖ {job.job_id} {t('cancelled_suffix', 'скасовано')}")

    # Reload history at most once per batch
    if need_history_reload:
        win._reload_history()

