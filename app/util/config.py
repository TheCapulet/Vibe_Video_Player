import json, os
from pathlib import Path
FILE = "config.json"
D = {
    "folders": [], "hw_accel": False, "text_size": 10, "preview_start": 120, 
    "card_width": 220, "show_static": True, "show_video": True, "volume": 70, 
    "sidebar_width": 350, "autohide_windowed": False, "playlist": [], "nicknames": {}
}
def load():
    data = D.copy()
    if os.path.exists(FILE):
        try:
            with open(FILE,"r") as f: data.update(json.load(f))
        except: pass
    # Force standardization on load
    data["folders"] = [Path(f).as_posix() for f in data["folders"]]
    return data
def save(data):
    # Force standardization on save
    data["folders"] = [Path(f).as_posix() for f in data["folders"]]
    with open(FILE,"w") as f: json.dump(data, f, indent=4)