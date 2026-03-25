"""PSK storage via OS keyring with plaintext fallback."""
import logging

_SERVICE = "LAN-FT"
_USERNAME = "psk"
_log = logging.getLogger("lan_ft.keyring")

try:
    import keyring as _keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False


def keyring_available() -> bool:
    return _KEYRING_AVAILABLE


def save_psk(psk: str) -> bool:
    """Save PSK to OS keyring. Returns True on success."""
    if not _KEYRING_AVAILABLE:
        return False
    try:
        if psk:
            _keyring.set_password(_SERVICE, _USERNAME, psk)
        else:
            _delete_psk()
        _log.info("PSK saved to OS keyring.")
        return True
    except Exception as e:
        _log.warning("Failed to save PSK to keyring: %s", e)
        return False


def load_psk() -> str | None:
    """Load PSK from OS keyring. Returns None if not found or unavailable."""
    if not _KEYRING_AVAILABLE:
        return None
    try:
        val = _keyring.get_password(_SERVICE, _USERNAME)
        return val or None
    except Exception as e:
        _log.warning("Failed to load PSK from keyring: %s", e)
        return None


def _delete_psk() -> None:
    if not _KEYRING_AVAILABLE:
        return
    try:
        _keyring.delete_password(_SERVICE, _USERNAME)
    except Exception:
        pass
