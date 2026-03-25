"""Persists transfer history with in-memory cache."""
import json
import threading
from datetime import datetime
from pathlib import Path

from config.settings import get_base_dir

_lock = threading.Lock()
_cache: list[dict] | None = None  # None = not loaded yet


def _history_path() -> Path:
    return get_base_dir() / "config" / "history.json"


def _load_from_disk() -> list[dict]:
    p = _history_path()
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def load_history() -> list[dict]:
    """Return history from in-memory cache (loads from disk on first call)."""
    global _cache
    with _lock:
        if _cache is None:
            _cache = _load_from_disk()
        return list(_cache)


def append_history(entry: dict) -> None:
    """Add one entry and keep last max_history records. Thread-safe."""
    global _cache
    from config.settings import load_settings
    max_records = load_settings().get("max_history", 200)

    with _lock:
        if _cache is None:
            _cache = _load_from_disk()
        entry.setdefault("time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        _cache.append(entry)
        _cache = _cache[-max_records:]
        _persist(_cache)


def clear_history() -> None:
    global _cache
    with _lock:
        _cache = []
        p = _history_path()
        if p.exists():
            p.unlink()


def reload_from_disk() -> list[dict]:
    """Force reload from disk (e.g. after external edit)."""
    global _cache
    with _lock:
        _cache = _load_from_disk()
        return list(_cache)


def _persist(history: list[dict]) -> None:
    p = _history_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        tmp.replace(p)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
