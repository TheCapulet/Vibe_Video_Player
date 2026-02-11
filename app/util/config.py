import json, os
from pathlib import Path
from app.util.logger import setup_app_logger

logger = setup_app_logger("CONFIG")

FILE = "config.json"
D = {
    "folders": [], "text_size": 10, "preview_start": 120, "card_width": 220,
    "show_static": True, "show_video": True, "volume": 70, "sidebar_width": 350,
    "autohide_windowed": False, "nicknames": {}, "playlist": [],
    # icon pack settings
    "installed_icon_pack": "default",
    "accepted_icon_licenses": {},
    "auto_accept_licenses": False
}

def load():
    data = D.copy()
    if os.path.exists(FILE):
        try:
            with open(FILE, "r") as f:
                data.update(json.load(f))
        except Exception:
            logger.exception("Failed to load config from %s", FILE)
    data["folders"] = [Path(f).as_posix() for f in data.get("folders", [])]
    return data


def save(data):
    try:
        data["folders"] = [Path(f).as_posix() for f in data.get("folders", [])]
        with open(FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception:
        logger.exception("Failed to save config to %s", FILE)