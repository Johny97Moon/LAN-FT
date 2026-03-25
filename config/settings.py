import json
import sys
from pathlib import Path

DEFAULT_PORT = 5001
CHUNK_SIZE = 65536  # 64 KB — стартовий розмір, адаптується динамічно в sender
APP_NAME = "LAN-FT"
DEFAULT_CONNECT_TIMEOUT = 30.0  # секунди

# Кешуємо base dir — обчислюється один раз
_base_dir: Path | None = None


def get_base_dir() -> Path:
    """Return base directory of the executable or script."""
    global _base_dir
    if _base_dir is None:
        if getattr(sys, "frozen", False):
            _base_dir = Path(sys.executable).parent
        else:
            _base_dir = Path(__file__).resolve().parent.parent
    return _base_dir


def get_config_path() -> Path:
    return get_base_dir() / "config" / "settings.json"


def load_settings() -> dict:
    path = get_config_path()
    defaults: dict = {
        "port": DEFAULT_PORT,
        "save_dir": str(Path.home() / "Downloads"),
        "max_file_size_mb": 0,          # 0 = no limit
        "max_parallel_transfers": 3,
        "overwrite_existing": "ask",    # ask | overwrite | skip
        "log_level": "INFO",
        "psk_storage": "keyring",       # keyring | plaintext
    }
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                defaults.update(json.load(f))
        except Exception:
            pass
    return defaults


def save_settings(data: dict) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
