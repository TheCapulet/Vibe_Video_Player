import os, urllib.request, sys, json, re
from pathlib import Path

print("--- APPLYING V79: PATH INDEPENDENCE & PORTABILITY FIX ---")

# Detect the actual project root where this patch is running
ROOT = Path(__file__).parent.absolute()

def write_f(p, c):
    full_path = ROOT / p
    os.makedirs(full_path.parent, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f: f.write(c.strip())
    print(f"FIXED: {p}")

def dl_assets():
    icons = {
        "playlist": "https://img.icons8.com/m/ios-filled/50/ffffff/menu.png",
        "folder": "https://img.icons8.com/m/ios-filled/50/ffffff/folder.png",
        "play": "https://img.icons8.com/m/ios-filled/50/ffffff/play.png",
        "pause": "https://img.icons8.com/m/ios-filled/50/ffffff/pause.png",
        "settings": "https://img.icons8.com/m/ios-filled/50/ffffff/settings.png"
    }
    icon_dir = ROOT / "resources" / "icons"
    os.makedirs(icon_dir, exist_ok=True)
    for name, url in icons.items():
        p = icon_dir / f"{name}.png"
        if not p.exists():
            try:
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-agent', 'Mozilla/5.0')]
                urllib.request.install_opener(opener).retrieve(url, str(p))
            except: pass

# --- 1. UPDATED BACKEND (Handle Safety) ---
backend_logic = r'''
import vlc, threading, time
class VLCBackend:
    def __init__(self):
        self.lock = threading.Lock()
        try:
            self.main_inst = vlc.Instance("--quiet", "--no-osd")
            self.main_player = self.main_inst.media_player_new()
            self.main_player.video_set_mouse_input(False)
            self.main_player.video_set_key_input(False)
            self.prev_inst = vlc.Instance("--quiet", "--no-audio", "--no-osd", "--avcodec-hw=none")
            self.prev_player = self.prev_inst.media_player_new()
            self.prev_player.video_set_mouse_input(False)
            self.ready = True
        except: self.ready = False
    def get_state_safe(self):
        try: return self.main_player.get_state() if self.ready else 0
        except: return 0
    def attach_main(self, h): 
        if self.ready: self.main_player.set_hwnd(h)
    def attach_prev(self, h): 
        if self.ready: self.prev_player.set_hwnd(h)
    def open_main(self, p):
        if not self.ready: return
        with self.lock:
            self.main_player.set_media(self.main_inst.media_new(p))
            self.main_player.play()
    def open_prev(self, p, start_sec=0):
        if not self.ready: return
        threading.Thread(target=self._exec_prev, args=(p, start_sec), daemon=True).start()
    def _exec_prev(self, p, s):
        with self.lock:
            try:
                self.prev_player.stop()
                self.prev_player.set_media(self.prev_inst.media_new(p))
                self.prev_player.play()
                for _ in range(10):
                    if self.prev_player.get_length() > 0: break
                    time.sleep(0.05)
                self.prev_player.set_time(s * 1000)
                self.prev_player.audio_set_mute(True)
            except: pass
    def stop_prev(self):
        if self.ready:
            with self.lock: self.prev_player.stop()
    def set_vol(self, v): 
        if self.ready: self.main_player.audio_set_volume(v)
    def release(self):
        if self.ready:
            self.main_player.stop(); self.prev_player.stop()
            self.main_inst.release(); self.prev_inst.release()
'''

# --- 2. UPDATED MAIN WINDOW (Absolute Paths) ---
ui_logic = r'''
import os, time, subprocess, hashlib, vlc, sys, threading, random, re
from pathlib import Path
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
import app.util.config as config
from app.ui.library import LibraryDelegate, get_h

# Detect Project Root based on this file's location (app/ui/main_window.py)
ROOT = Path(__file__).parent.parent.parent.absolute()

def nat_sort(s): return [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', s)]

class ClickSlider(QSlider):
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            v = self.minimum() + ((self.maximum()-self.minimum())*e.position().x())/self.width()
            self.setValue(int(v)); self.sliderMoved.emit(self.value())
        super().mousePressEvent(e)

class VideoWidget(QWidget):
    double_clicked = Signal(); mouse_moved = Signal()
    def __init__(self, parent=None):
        super().__init__(parent); self.setMouseTracking(True)
    def mouseDoubleClickEvent(self, e): self.double_clicked.emit()
    def mouseMoveEvent(self, e): self.mouse_moved.emit(); super().mouseMoveEvent(e)

class MainWindow(QMainWindow):
    def __init__(self, player, backend):
        super().__init__(); self.player, self.backend = player, backend
        self.cfg = config.load(); self.checked_paths = set()
        self.setWindowTitle("Vibe Video Player"); self.resize(1600, 900)
        self.setStyleSheet("background:#0a0a0a; color:white;"); self.setMouseTracking(True)
        
        # Absolute Asset Loading
        def icn(k): 
            icon_p = ROOT / "resources" / "icons" / f"{k}.png"
            return QIcon(str(icon_p))

        self.icns = {k: icn(k) for k in ["play","pause","playlist","folder","settings"]}
        
        # Absolute Worker Launch
        worker_script = ROOT / "app" / "util" / "worker.py"
        self.worker = subprocess.Popen([sys.executable, str(worker_script)], stdin=subprocess.PIPE, text=True, bufsize=1)
        
        cw = QWidget(); self.setCentralWidget(cw); root_lay = QHBoxLayout(cw); root_lay.setContentsMargins(0,0,0,0); root_lay.setSpacing(0)
        self.split = QSplitter(Qt.Horizontal); root_lay.addWidget(self.split); self.split.splitterMoved.connect(self.on_split)

        # LEFT
        self.sb_l = QWidget(); l_lay = QVBoxLayout(self.sb_l); l_lay.setContentsMargins(0,0,0,0)
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True); self.tree.setIndentation(15)
        self.tree.setColumnCount(1); self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection); self.tree.setMouseTracking(True)
        self.tree.setStyleSheet("background:#111; border:none;")
        self.tree.setItemDelegate(LibraryDelegate(self.tree, self.cfg, self.checked_paths)); l_lay.addWidget(self.tree)
        self.ov = QWidget(self.tree.viewport()); self.ov.hide(); self.ov.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.backend.attach_prev(int(self.ov.winId()))

        # Settings
        self.opt_shelf = QWidget(); self.opt_shelf.hide(); self.opt_shelf.setStyleSheet("background:#181818; border-top:1px solid #333;")
        grid = QGridLayout(self.opt_shelf); self.tog_hide = QCheckBox("Autohide Windowed"); self.tog_hide.setChecked(self.cfg["autohide_windowed"])
        self.tog_hide.toggled.connect(self.save_toggles)
        def mk_sl(lbl, key, min_v, max_v):
            box = QWidget(); bl = QVBoxLayout(box); val = self.cfg[key]
            t = QLabel(f"{lbl}: {val}"); t.setStyleSheet("font-size:10px; color:#888;")
            s = QSlider(Qt.Horizontal); s.setRange(min_v, max_v); s.setValue(val)
            s.valueChanged.connect(lambda v, k=key, lb=t, name=lbl: self.set_vis_cfg(k, v, lb, name))
            bl.addWidget(t); bl.addWidget(s); return box
        grid.addWidget(self.tog_hide, 0, 0)
        grid.addWidget(mk_sl("Text", "text_size", 8, 30), 0, 1)
        grid.addWidget(mk_sl("Size", "card_width", 100, 450), 1, 1)
        l_lay.addWidget(self.opt_shelf)

        footer = QHBoxLayout(); footer.setContentsMargins(5,5,5,5)
        btn_opts = QPushButton(icon=self.icns["settings"]); btn_opts.clicked.connect(lambda: self.opt_shelf.setVisible(not self.opt_shelf.isVisible()))
        btn_add = QPushButton("+", clicked=self.add_f); btn_add.setFixedSize(30,30)
        footer.addWidget(btn_opts); footer.addStretch(); footer.addWidget(btn_add); l_lay.addLayout(footer); self.split.addWidget(self.sb_l)

        # CENTER
        self.center_pane = QWidget(); self.center_lay = QVBoxLayout(self.center_pane); self.center_lay.setContentsMargins(0,0,0,0)
        self.v_out = VideoWidget(); self.v_out.setStyleSheet("background:black;"); self.v_out.double_clicked.connect(self.toggle_fs); self.v_out.mouse_moved.connect(self.wake_ui)
        self.center_lay.addWidget(self.v_out, 1)
        self.control_panel = QWidget(); cp_lay = QVBoxLayout(self.control_panel); cp_lay.setContentsMargins(0,0,0,0)
        self.sk = ClickSlider(Qt.Horizontal); self.sk.setRange(0, 1000); cp_lay.addWidget(self.sk)
        self.sk.sliderMoved.connect(lambda v: self.backend.main_player.set_time(int((v/1000)*self.backend.main_player.get_length())))
        ctrl_row = QHBoxLayout(); ctrl_row.setContentsMargins(10,5,10,10)
        bt_l = QPushButton(icon=self.icns["playlist"]); bt_l.clicked.connect(lambda: self.sb_l.setVisible(not self.sb_l.isVisible()))
        self.bp = QPushButton(icon=self.icns["play"]); self.bp.clicked.connect(self.backend.main_player.pause)
        self.vol = QSlider(Qt.Horizontal); self.vol.setFixedWidth(100); self.vol.setRange(0, 100); self.vol.setValue(self.cfg["volume"]); self.vol.valueChanged.connect(self.set_vol_save)
        self.lbl_t = QLabel("0:00 / 0:00"); bt_r = QPushButton(icon=self.icns["playlist"]); bt_r.clicked.connect(lambda: self.sb_r.setVisible(not self.sb_r.isVisible()))
        ctrl_row.addWidget(bt_l); ctrl_row.addSpacing(10); ctrl_row.addWidget(self.bp); ctrl_row.addStretch()
        ctrl_row.addWidget(QLabel("Vol:")); ctrl_row.addWidget(self.vol); ctrl_row.addWidget(self.lbl_t); ctrl_row.addSpacing(10); ctrl_row.addWidget(bt_r)
        cp_lay.addLayout(ctrl_row); self.center_lay.addWidget(self.control_panel); self.backend.attach_main(int(self.v_out.winId())); self.split.addWidget(self.center_pane)

        # RIGHT
        self.sb_r = QWidget(); self.sb_r.setFixedWidth(300); self.sb_r.setStyleSheet("background:#111; border-left:1px solid #222;")
        rl = QVBoxLayout(self.sb_r); self.plist = QListWidget(); self.plist.itemDoubleClicked.connect(lambda i: self.p_m(i.data(Qt.UserRole)))
        rl.addWidget(QLabel("PLAYLIST")); rl.addWidget(self.plist); self.split.addWidget(self.sb_r)

        self.hide_timer = QTimer(); self.hide_timer.setInterval(3000); self.hide_timer.setSingleShot(True); self.hide_timer.timeout.connect(self.hide_ui)
        self.sb_l.hide(); self.sb_r.hide()
        self.tree.itemExpanded.connect(self.on_expand); self.tree.itemEntered.connect(self.on_hover)
        self.tree.itemPressed.connect(self.on_tree_click); self.tree.itemDoubleClicked.connect(self.on_activated)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu); self.tree.customContextMenuRequested.connect(self.on_context)
        self.tm = QTimer(); self.tm.setInterval(200); self.tm.timeout.connect(self.upd); self.tm.start()
        self.backend.set_vol(self.cfg["volume"]); QTimer.singleShot(500, self.ref_initial)

    def on_split(self, pos, idx): 
        if idx == 1: self.cfg["sidebar_width"] = pos; config.save(self.cfg)
    def wake_ui(self): self.control_panel.show(); self.setCursor(Qt.ArrowCursor); self.hide_timer.start()
    def hide_ui(self):
        if self.backend.get_state_safe() == 3 and (self.isFullScreen() or self.cfg["autohide_windowed"]):
            self.control_panel.hide(); self.sb_l.hide(); self.sb_r.hide(); self.setCursor(Qt.BlankCursor if self.isFullScreen() else Qt.ArrowCursor)
    def toggle_fs(self): self.showNormal() if self.isFullScreen() else (self.showFullScreen(), self.hide_timer.start())
    def set_vol_save(self, v): self.cfg["volume"] = v; config.save(self.cfg); self.backend.set_vol(v)
    def save_toggles(self): self.cfg["autohide_windowed"] = self.tog_hide.isChecked(); config.save(self.cfg)
    def set_vis_cfg(self, k, v, lb, name): 
        self.cfg[k] = v; lb.setText(f"{name}: {v}"); config.save(self.cfg)
        self.tree.updateGeometries(); self.tree.viewport().update()
    
    def add_f(self):
        p = QFileDialog.getExistingDirectory(self, "Add Folder")
        if p and p not in self.cfg["folders"]: self.cfg["folders"].append(p); config.save(self.cfg); self.ref()
    def ref_initial(self): self.split.setSizes([self.cfg["sidebar_width"], 800, 300]); self.ref()
    def ref(self):
        self.tree.clear()
        for f in self.cfg["folders"]:
            if os.path.exists(f):
                it = QTreeWidgetItem(self.tree, [self.cfg["nicknames"].get(f, os.path.basename(f))])
                it.setIcon(0, self.icns["folder"]); it.setData(0, Qt.UserRole, f); it.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
    def on_expand(self, item):
        if item.childCount() > 0: return
        p = item.data(0, Qt.UserRole)
        try:
            for e in sorted(Path(p).iterdir()):
                if e.is_dir():
                    n = self.cfg["nicknames"].get(str(e.absolute()), e.name)
                    c = QTreeWidgetItem(item, [n]); c.setIcon(0, self.icns["folder"]); c.setData(0, Qt.UserRole, str(e.absolute())); c.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                elif e.suffix.lower() in ('.mp4','.mkv','.avi'):
                    v = QTreeWidgetItem(item, [e.name]); v.setData(0, Qt.UserRole, str(e.absolute()))
                    v.setFlags(v.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable); v.setCheckState(0, Qt.Unchecked)
        except: pass
    def on_tree_click(self, it, col):
        p = it.data(0, Qt.UserRole)
        if p and not os.path.isdir(p) and self.tree.viewport().mapFromGlobal(QCursor.pos()).x() < 35:
            if p in self.checked_paths: self.checked_paths.remove(p)
            else: self.checked_paths.add(p)
            self.tree.viewport().update()
    def on_hover(self, it, col):
        p = it.data(0, Qt.UserRole)
        if self.cfg["show_video"] and p and not os.path.isdir(p):
            rect = self.tree.visualItemRect(it); tw = self.cfg["card_width"]
            self.ov.setFixedSize(tw, int(tw*0.56)); self.ov.move(self.mapFromGlobal(self.tree.viewport().mapToGlobal(rect.topLeft() + QPoint(30, 5))))
            self.ov.show(); self.ov.raise_(); self.backend.open_prev(p, self.cfg["preview_start"])
        else: self.ov.hide(); self.backend.stop_prev()
    def on_activated(self, it, col):
        p = it.data(0, Qt.UserRole)
        if p and not os.path.isdir(p): self.p_m(p)
    def on_context(self, pos):
        it = self.tree.itemAt(pos); checked = list(self.checked_paths)
        if not it and not checked: return
        menu = QMenu(); p = it.data(0, Qt.UserRole) if it else None
        if checked or (p and not os.path.isdir(p)):
            if menu.addAction("Add Selected to Playlist") == menu.exec(QCursor.pos()):
                for path in (checked if checked else [p]): self.add_to_pl(path)
                self.checked_paths.clear(); self.tree.viewport().update()
        elif p and os.path.isdir(p):
            p_all = menu.addAction("Add All to Playlist"); p_rnd = menu.addAction("Add All Randomized")
            if it.parent() is None: menu.addAction("Remove Shelf", lambda: self.rem_fld(p))
            act = menu.exec(QCursor.pos())
            if act in [p_all, p_rnd]:
                vids = [str(x) for x in Path(p).rglob("*") if x.suffix.lower() in ('.mp4','.mkv','.avi')]
                if act == p_rnd: random.shuffle(vids)
                else: vids.sort(key=nat_sort)
                for v in vids: self.add_to_pl(v)
    def add_to_pl(self, path):
        parts = Path(path).parts
        info = f"{parts[-3]} | {parts[-2]} | {parts[-1]}" if len(parts) >= 3 else Path(path).name
        for i in range(self.plist.count()):
            if self.plist.item(i).data(Qt.UserRole) == path: return
        li = QListWidgetItem(info); li.setData(Qt.UserRole, path); self.plist.addItem(li)
        self.sort_pl()
    def sort_pl(self):
        items = []
        for i in range(self.plist.count()):
            it = self.plist.item(i); items.append({'i': it.text(), 'p': it.data(Qt.UserRole)})
        items.sort(key=lambda x: nat_sort(x['p'])); self.plist.clear()
        for x in items: li = QListWidgetItem(x['i'], data=x['p']); self.plist.addItem(li)
    def p_m(self, p): 
        self.ov.hide(); self.backend.stop_prev(); self.backend.open_main(p)
        for i in range(self.plist.count()):
            if self.plist.item(i).data(Qt.UserRole) == p: self.plist.setCurrentRow(i); break
    def play_next(self):
        if self.plist.count() == 0: return
        idx = (self.plist.currentRow() + 1) % self.plist.count()
        self.plist.setCurrentRow(idx); self.p_m(self.plist.currentItem().data(Qt.UserRole))
    def upd(self):
        m_pos = self.tree.viewport().mapFromGlobal(QCursor.pos())
        if self.ov.isVisible() and not self.tree.viewport().rect().contains(m_pos): self.ov.hide(); self.backend.stop_prev()
        m = self.backend.main_player; state = self.backend.get_state_safe()
        self.bp.setIcon(self.icns["pause" if state == 3 else "play"])
        if state == 6 and self.plist.count() > 0: self.play_next()
        d, cur = m.get_length(), m.get_time()
        if d > 0 and not self.sk.isSliderDown(): self.sk.setValue(int((cur/d)*1000))
        if d > 0: self.lbl_t.setText(f"{cur//60000}:{(cur//1000)%60:02} / {d//60000}:{(d//1000)%60:02}")
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value(); p = str(item.data(0, Qt.UserRole))
            if item.data(0, Qt.DecorationRole) is None and not os.path.isdir(p) and p != "None":
                tp = os.path.join(str(ROOT), "resources", "thumbs", f"{get_h(p)}.jpg")
                if os.path.exists(tp): item.setData(0, Qt.DecorationRole, QPixmap(tp))
                else:
                    try:
                        self.worker.stdin.write(f"{p}|{self.cfg['preview_start']}\n")
                        self.worker.stdin.flush()
                    except BrokenPipeError: pass
            it += 1
    def closeEvent(self, e): self.worker.terminate(); self.backend.release(); e.accept()
'''

if __name__ == "__main__":
    dl_assets()
    write_f("app/core/vlc_backend.py", backend_logic)
    write_f("app/ui/main_window.py", ui_logic)
    print("\n--- PHASE 79 PORTABLE READY. RUN app/main.py ---")