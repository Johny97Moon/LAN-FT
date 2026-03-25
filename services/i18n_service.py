import json
import logging
from pathlib import Path
from config.settings import get_base_dir

_log = logging.getLogger("lan_ft.i18n")

_translations = {}
_current_lang = "ua"

def init_i18n(lang="ua"):
    global _current_lang, _translations
    _current_lang = lang
    i18n_dir = get_base_dir() / "i18n"
    lang_file = i18n_dir / f"{lang}.json"
    
    if not lang_file.exists():
        _log.warning(f"Translation file {lang_file} not found. Falling back to default.")
        if lang != "en":
             # Try English fallback
             lang_file = i18n_dir / "en.json"
    
    if lang_file.exists():
        try:
            with open(lang_file, "r", encoding="utf-8") as f:
                _translations = json.load(f)
        except Exception as e:
            _log.error(f"Failed to load translation: {e}")
            _translations = {}
    else:
        _translations = {}

def t(key, default=None):
    """Translate a key."""
    return _translations.get(key, default or key)

def get_lang():
    return _current_lang
