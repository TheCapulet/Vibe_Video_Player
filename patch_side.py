import os
import time
import threading
import vlc

print("--- STARTING CLEAN SLATE PATCH (VLC-ONLY) ---")

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip())
    print(f"PATCHED: {path}")

# --- 1. CONFIG UTILITY ---
config_code = r"""
import json, os
FILE = "config.json"
def load_folders():
    if os.path.exists(FILE):
        try:
            with open(FILE, "r") as f: return json.load(f).get("folders", [])
        except: return []
    return []
def save_folders(fld):
    with open(FILE, "w") as f: json.dump({"folders": fld}, f)
"""

# --- 2. VLC BACKEND (Dual Player Support) ---
backend_code = r"""
import vlc
class VLCBackend:
    def __init__(self):
        # We use one instance for everything
        self._instance = vlc.Instance("--no-video-title-show", "--quiet")
        self.main_player = self._instance.media_player_new()
        self.preview_player = self._instance.media_player_new()
        self.preview_player.audio_set_mute(True)

    def attach_main(self, wid):
        if hasattr(self.main_player, "set_hwnd"): self.main_player.set_hwnd(wid)
        elif hasattr(self.main_player, "set_xwindow"): self.main_player.set_xwindow(wid)

    def attach_preview(self, wid):
        if hasattr(self.preview_player, "set_hwnd"): self.preview_player.set_hwnd(wid)
        elif hasattr(self.preview_player, "set_xwindow"): self.preview_player.set_xwindow(wid)

    def open_main(self, p):
        m = self._instance.media_new(p)
        self.main_player.set_media(m)
    
    def open_preview(self, p):
        m = self._instance.media_new(p)
        self.preview_player.set_media(m)

    def release(self):
        self.main_player.stop(); self.main_player.release()
        self.preview_player.stop(); self.preview_player.release()
        self._instance.release()
"""

# --- 3. MAIN UI (Library + Hover Previews) ---
ui_code = r"""
import os, time, threading, vlc
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
from app.util.config import load_folders, save_folders

class Thumbnailer:
    @staticmethod
    def get_thumb_path(video_path):
        thumb_dir = os.path.join("resources", "thumbs")
        os.makedirs(thumb_dir, exist_ok=True)
        # Create a unique filename based on the path
        safe_name = "".join([c if c.isalnum() else "_" for c in os.path.abspath(video_path)])
        return os.path.join(thumb_dir, f"{safe_name}.jpg")

    @staticmethod
    def create_snapshot(video_path, output_path):
        # Temporary VLC instance to grab a frame
        inst = vlc.Instance("--intf=dummy", "--vout=dummy", "--no-audio")
        p = inst.media_player_new()
        m = inst.media_new(video_path)
        p.set_media(m)
        p.play()
        
        # Wait for duration/init
        for _ in range(20):
            if p.get_length() > 0: break
            time.sleep(0.1)
        
        dur = p.get_length()
        target = 120000 if dur > 120000 else dur // 2
        p.set_time(target)
        time.sleep(0.4) # Wait for frame seek
        
        p.video_take_snapshot(0, output_path, 320, 180)
        p.stop(); p.release(); inst.release()

class VideoCard(QWidget):
    clicked = Signal(str)
    hovered = Signal(str, QWidget)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.setFixedWidth(280)
        self.lay = QVBoxLayout(self)
        
        self.thumb_label = QLabel("Initializing...")
        self.thumb_label.setFixedSize(260, 146)
        self.thumb_label.setStyleSheet("background: black; border-radius: 4px;")
        self.thumb_label.setAlignment(Qt.AlignCenter)
        
        name = QLabel(os.path.basename(path))
        name.setStyleSheet("font-size: 11px; color: #888;")
        name.setWordWrap(True)
        
        self.lay.addWidget(self.thumb_label)
        self.lay.addWidget(name)
        
        self.thumb_path = Thumbnailer.get_thumb_path(path)
        threading.Thread(target=self.process_thumb, daemon=True).start()

    def process_thumb(self):
        if not os.path.exists(self.thumb_path):
            Thumbnailer.create_snapshot(self.path, self.thumb_path)
        
        if os.path.exists(self.thumb_path):
            pix = QPixmap(self.thumb_path).scaled(260, 146, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            QMetaObject.invokeMethod(self.thumb_label, "setPixmap", Qt.QueuedConnection, Q_ARG(QPixmap, pix))
        else:
            QMetaObject.invokeMethod(self.thumb_label, "setText", Qt.QueuedConnection, Q_ARG(str, "No Preview"))

    def enterEvent(self, e):
        self.hovered.emit(self.path, self.thumb_label)
        super().enterEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.clicked.emit(self.path)

class MainWindow(QMainWindow):
    def __init__(self, player, backend):
        super().__init__()
        self.player, self.backend = player, backend
        self.last_path = None
        self.setWindowTitle("VLC Player (Sane Library)"); self.resize(1500, 900)
        self.setStyleSheet("background: #121212; color: white;")

        # Icons
        icn_dir = "resources/icons"
        self.icns = {k: QIcon(f"{icn_dir}/{k}.png") for k in ["play","pause","open","fullscreen","menu"]}

        self.cw = QWidget(); self.setCentralWidget(self.cw)
        self.root = QHBoxLayout(self.cw); self.root.setContentsMargins(0,0,0,0)

        # --- LIBRARY SIDEBAR ---
        self.sidebar = QWidget(); self.sidebar.setFixedWidth(320)
        self.sidebar.setStyleSheet("background: #181818; border-right: 1px solid #333;")
        self.sb_lay = QVBoxLayout(self.sidebar)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.sb_container = QWidget()
        self.sb_container_lay = QVBoxLayout(self.sb_container)
        self.sb_container_lay.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.sb_container)
        
        self.sb_lay.addWidget(QLabel("LIBRARY"))
        self.sb_lay.addWidget(self.scroll)
        self.btn_add = QPushButton("+ Add Folder"); self.btn_add.clicked.connect(self.browse_folder)
        self.sb_lay.addWidget(self.btn_add)
        self.root.addWidget(self.sidebar)

        # --- MAIN PLAYER ---
        right = QWidget(); r_lay = QVBoxLayout(right); self.root.addWidget(right)
        self.vid = QWidget(); self.vid.setStyleSheet("background: black;"); r_lay.addWidget(self.vid, 1)
        
        self.sk = QSlider(Qt.Horizontal); self.sk.setRange(0, 1000)
        self.sk.sliderMoved.connect(self.user_seek)
        r_lay.addWidget(self.sk)

        # Preview Overlay
        self.preview_overlay = QWidget(self)
        self.preview_overlay.setFixedSize(260, 146)
        self.preview_overlay.hide()
        self.backend.attach_preview(int(self.preview_overlay.winId()))

        ctrl = QHBoxLayout()
        self.b_menu = QPushButton(); self.b_menu.setIcon(self.icns["menu"])
        self.b_menu.clicked.connect(lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))
        self.b_play = QPushButton(); self.b_play.setIcon(self.icns["play"])
        self.b_play.clicked.connect(self.backend.main_player.pause)
        
        self.lbl = QLabel("00:00 / 00:00")
        vol = QSlider(Qt.Horizontal); vol.setFixedWidth(80); vol.setValue(70)
        vol.valueChanged.connect(self.backend.main_player.audio_set_volume)

        for b in [self.b_menu, self.b_play]: b.setFixedSize(40,40); b.setStyleSheet("border:none; background:transparent;")
        ctrl.addWidget(self.b_menu); ctrl.addWidget(self.b_play); ctrl.addStretch()
        ctrl.addWidget(QLabel("Vol:")); ctrl.addWidget(vol); ctrl.addWidget(self.lbl)
        r_lay.addLayout(ctrl)

        self.backend.attach_main(int(self.vid.winId()))
        self.tm = QTimer(); self.tm.setInterval(100); self.tm.timeout.connect(self.upd); self.tm.start()
        self.refresh_library()

    def browse_folder(self):
        p = QFileDialog.getExistingDirectory(self, "Add Folder")
        if p:
            f = load_folders()
            if p not in f: f.append(p); save_folders(f); self.refresh_library()

    def refresh_library(self):
        for i in reversed(range(self.sb_container_lay.count())): 
            self.sb_container_lay.itemAt(i).widget().setParent(None)
        
        for fld in load_folders():
            group = QGroupBox(os.path.basename(fld))
            group.setStyleSheet("QGroupBox { border-top: 1px solid #333; margin-top: 15px; padding-top: 10px; color: #666; font-weight: bold; }")
            lay = QVBoxLayout(group)
            exts = ('.mp4', '.mkv', '.avi', '.mov')
            try:
                files = [os.path.join(fld, f) for f in os.listdir(fld) if f.lower().endswith(exts)]
                for f in sorted(files):
                    card = VideoCard(f)
                    card.clicked.connect(self.open_main_file)
                    card.hovered.connect(self.start_preview)
                    lay.addWidget(card)
            except: pass
            self.sb_container_lay.addWidget(group)

    def start_preview(self, path, widget):
        pos = widget.mapToGlobal(QPoint(0,0))
        self.preview_overlay.move(self.mapFromGlobal(pos))
        self.preview_overlay.show()
        self.backend.open_preview(path)
        self.backend.preview_player.play()

    def leaveEvent(self, e):
        self.preview_overlay.hide()
        self.backend.preview_player.stop()
        super().leaveEvent(e)

    def open_main_file(self, path):
        self.last_path = path; self.backend.open_main(path); self.backend.main_player.play()

    def user_seek(self, v):
        d = self.backend.main_player.get_length()
        if d > 0: self.backend.main_player.set_time(int((v/1000)*d))

    def upd(self):
        import vlc
        m = self.backend.main_player
        self.b_play.setIcon(self.icns["pause"] if m.get_state() == vlc.State.Playing else self.icns["play"])
        d, c = m.get_length(), m.get_time()
        if d > 0:
            if not self.sk.isSliderDown(): self.sk.setValue(int((c/d)*1000))
            self.lbl.setText(f"{self.fmt(c)} / {self.fmt(d)}")

    def fmt(self, ms):
        s, m, h = (ms//1000)%60, (ms//60000)%60, (ms//3600000)
        return f"{h:02}:{m:02}:{s:02}" if h > 0 else f"{m:02}:{s:02}"

    def closeEvent(self, e): self.backend.release(); e.accept()
"""

if __name__ == "__main__":
    write_file("app/util/config.py", config_code)
    write_file("app/core/vlc_backend.py", backend_code)
    write_file("app/ui/main_window.py", ui_code)
    print("\n--- CLEAN SLATE PATCH COMPLETE. RUN app/main.py ---")