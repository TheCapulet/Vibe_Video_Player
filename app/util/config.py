import json, os
from pathlib import Path
FILE = "config.json"
D = {
    "folders": [], "text_size": 10, "preview_start": 120, "card_width": 220, 
    "show_static": True, "show_video": True, "volume": 70, "sidebar_width": 350, 
    "autohide_windowed": False, "nicknames": {}, "playlist": []
}
def load():
    data = D.copy()
    if os.path.exists(FILE):
        try:
            with open(FILE,"r") as f:
                saved = json.load(f)
                for k,v in saved.items(): data[k] = v
        except: pass
    data["folders"] = [str(Path(f).as_posix()) for f in data["folders"]]
    return data
def save(data):
    with open(FILE,"w") as f: json.dump(data, f, indent=4)