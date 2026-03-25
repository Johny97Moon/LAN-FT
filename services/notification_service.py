"""
Notifications: sound + Windows toast.
Falls back gracefully if libraries are missing.
"""
import threading

# ── Sound ────────────────────────────────────────────────────────────────────

def play_sound(success: bool = True) -> None:
    """Play a system sound in a background thread (non-blocking)."""
    threading.Thread(target=_play, args=(success,), daemon=True).start()


def _play(success: bool) -> None:
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_OK if success else winsound.MB_ICONHAND)
    except Exception:
        pass


# ── Windows Toast ─────────────────────────────────────────────────────────────

# Кешуємо notifier щоб не створювати новий об'єкт при кожному виклику
_toaster = None
_toast_backend: str | None = None
_toast_init_lock = threading.Lock()
_toast_initialized = threading.Event()


def _init_toast_backend():
    global _toaster, _toast_backend
    if _toast_initialized.is_set():
        return
    with _toast_init_lock:
        if _toast_initialized.is_set():
            return
        try:
            from win10toast import ToastNotifier
            _toaster = ToastNotifier()
            _toast_backend = "win10toast"
        except Exception:
            pass
        if _toast_backend is None:
            try:
                from plyer import notification as _plyer  # noqa: F401
                _toast_backend = "plyer"
            except Exception:
                pass
        if _toast_backend is None:
            _toast_backend = "none"
        _toast_initialized.set()


def show_toast(title: str, message: str, duration: int = 4) -> None:
    """Show a native OS toast notification. Non-blocking."""
    threading.Thread(target=_toast, args=(title, message, duration), daemon=True).start()


def _toast(title: str, message: str, duration: int) -> None:
    _init_toast_backend()
    if _toast_backend == "win10toast" and _toaster:
        try:
            _toaster.show_toast(title, message, duration=duration, threaded=True)
            return
        except Exception:
            pass
    elif _toast_backend == "plyer":
        try:
            from plyer import notification
            notification.notify(title=title, message=message, timeout=duration)
            return
        except Exception:
            pass
