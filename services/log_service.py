"""Centralized file logging for LAN-FT."""
import logging
import logging.handlers
from pathlib import Path

from config.settings import get_base_dir

_logger: logging.Logger | None = None


def get_logger(name: str = "lan_ft") -> logging.Logger:
    """Return the application logger, initializing it on first call."""
    global _logger
    if _logger is None:
        _logger = _setup_logger()
    return logging.getLogger(name)


def _setup_logger() -> logging.Logger:
    log_path = get_base_dir() / "config" / "app.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("lan_ft")
    logger.setLevel(logging.DEBUG)

    # Rotating file handler: 2 MB per file, keep 3 backups
    fh = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(fh)
    return logger


def reconfigure(level: str = "INFO") -> None:
    """Change log level at runtime (called after settings change)."""
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.getLogger("lan_ft").setLevel(lvl)
