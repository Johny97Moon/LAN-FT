"""LAN File Transfer - entry point."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Initialize logger before anything else
from services.log_service import get_logger
from services.i18n_service import init_i18n
from config.settings import load_settings

get_logger()
settings = load_settings()
init_i18n(settings.get("language", "ua"))

from ui.main_window import MainWindow


def main():
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()
