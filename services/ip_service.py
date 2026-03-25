import socket

_cached_ip: str | None = None


def get_local_ip() -> str:
    """Return the local LAN IP. Result is cached after first call."""
    global _cached_ip
    if _cached_ip is not None:
        return _cached_ip
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            _cached_ip = s.getsockname()[0]
    except Exception:
        _cached_ip = "127.0.0.1"
    return _cached_ip
