import os, urllib.request, sys, json, re
from pathlib import Path

print("--- APPLYING V81: UNIFIED TREE & VISIBILITY FIX ---")

# Detect Project Root (Where patch.py is running)
ROOT = Path(__file__).parent.absolute()

def write_f(p, c):
    full_path = ROOT / p
    os.makedirs(full_path.parent, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f: f.write(c.strip())
    print(f"DONE: {p}")

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
        try:
            opener = urllib.request.build_opener()
            opener.addheaders = [('User-agent', 'Mozilla/5.0')]
            urllib.request.install_opener(opener).retrieve(url, str(p))
        except: pass

# --- UI LOGIC (Unified Single Column) ---
ui_logic = r'''
import os, time, subprocess, hashlib, vlc, sys, threading, random, re
from pathlib import Path
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
import app.util.config as config

# Detect Root from within UI
ROOT = Path(__file__).parent.parent.parent.absolute()

def get_h(p): return hashlib.md5(p.lower().replace("\\","/").encode()).hexdigest()
def nat_sort(s): return [int(t) if t.isdigit() else t.lower() for t in re.split('([0-9]+)', s)]

class ClickSlider(QSlider):
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            val = self.minimum() + ((self.maximum()-self.minimum())*e.position().x())/self.width()
            self.setValue(int(val)); self.sliderMoved.emit(self.value())
        super().mousePressEvent(e)

class VideoWidget(QWidget):
    double_clicked = Signal(); mouse_moved = Signal()
    def __init__(self, parent=None):
        super().__init__(parent); self.setMouseTracking(True)
    def mouseDoubleClickEvent(self, e): self.double_clicked.emit()
    def mouseMoveEvent(self, e): self.mouse_moved.emit(); super().mouseMoveEvent(e)

class LibraryDelegate(QStyledItemDelegate):
    def __init__(self, parent, cfg, checked_set):
        super().__init__(parent); self.cfg = cfg; self.checked_set = checked_set
    
    def paint(self, painter, option, index):
        painter.save()
        if option.state & QStyle.State_Selected: painter.fillRect(option.rect, QColor(45, 45, 45))
        p = index.data(Qt.UserRole)
        # Check if it is a video file
        is_video = any(str(p).lower().endswith(ex) for ex in ['.mp4','.mkv','.avi'])
        
        if is_video:
            tw, th = self.cfg["card_width"], int(self.cfg["card_width"] * 0.56)
            # 1. Checkbox (Hit zone)
            cb_rect = QRect(option.rect.left() + 8, option.rect.top() + (th // 2) - 4, 18, 18)
            opt = QStyleOptionButton(); opt.rect = cb_rect; opt.state = QStyle.State_Enabled
            opt.state |= QStyle.State_On if p in self.checked_set else QStyle.State_Off
            QApplication.style().drawControl(QStyle.CE_CheckBox, opt, painter)
            # 2. Thumbnail
            r_img = QRect(option.rect.left() + 35, option.rect.top() + 5, tw, th)
            painter.fillRect(r_img, Qt.black)
            pix = index.data(Qt.DecorationRole)
            if isinstance(pix, QPixmap): painter.drawPixmap(r_img, pix.scaled(r_img.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            # 3. Text
            r_txt = QRect(option.rect.left() + 35, option.rect.top() + th + 8, tw, self.cfg["text_size"] * 2.5)
            painter.setPen(QColor(200, 200, 200))
            f = painter.font(); f.setPointSize(self.cfg["text_size"]); painter.setFont(f)
            painter.drawText(r_txt, Qt.AlignLeft | Qt.TextWordWrap, index.data(Qt.DisplayRole))
        else:
            # Draw Folder Row using default OS style
            super().paint(painter, option, index)
        painter.restore()

    def sizeHint(self, option, index):
        p = index.data(Qt.UserRole)
        is_video = any(str(p).lower().endswith(ex) for ex in ['.mp4','.mkv','.avi'])
        if is_video:
            tw = self.cfg["card_width"]
            return QSize(tw + 45, int(tw * 0.56) + (self.cfg["text_size"] * 2.5) + 15)
        return QSize(200, 32)

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonPress and event.pos().x() < option.rect.left() + 35:
            p = index.data(Qt.UserRole)
            if p in self.checked_set: self.checked_set.remove(p)
            else: self.checked_set.add(p)
            model.dataChanged.emit(index, index); return True
        return super().editorEvent(event, model, option, index)

class MainWindow(QMainWindow):
    def __init__(self, player, backend):
        super().__init__(); self.player, self.backend = player, backend
        self.cfg = config.load(); self.checked_paths = set()
        self.setWindowTitle("Vibe Video Player"); self.resize(1600, 900)
        self.setStyleSheet("background:#0a0a0a; color:white;"); self.setMouseTracking(True)
        
        def icn(k): return QIcon(str(ROOT / "resources" / "icons" / f"{k}.png"))
        self.icns = {k: icn(k) for k in ["play","pause","playlist","folder","settings"]}
        self.worker = subprocess.Popen([sys.executable, str(ROOT / "app" / "util" / "worker.py")], stdin=subprocess.PIPE, text=True, bufsize=1)
        
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
        grid.addWidget(self.tog_hide, 0, 0); grid.addWidget(mk_sl("Text", "text_size", 8, 30), 0, 1); grid.addWidget(mk_sl("Size", "card_width", 100, 450), 1, 1)
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
        self.tree.itemExpanded.connect(self.on_expand); self.tree.itemEntered.connect(self.on_hover); self.tree.itemPressed.connect(self.on_tree_click)
        self.tree.itemDoubleClicked.connect(self.on_activated); self.tree.setContextMenuPolicy(Qt.CustomContextMenu); self.tree.customContextMenuRequested.connect(self.on_context)
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
        if p and not os.path.isdir(p) and self.tree.viewport().mapFromGlobal(QCursor.pos()).x() < 30:
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
                for path in (checked if checked else [p]):
                    pts = Path(path).parts
                    info = f"{pts[-3]} | {pts[-2]} | {pts[-1]}" if len(pts) >= 3 else Path(path).name
                    li = QListWidgetItem(info); li.setData(Qt.UserRole, path); self.plist.addItem(li)
                self.checked_paths.clear(); self.tree.viewport().update()
        elif p and os.path.isdir(p):
            p_all = menu.addAction("Add All to Playlist"); p_rnd = menu.addAction("Add All Randomized"); rem = menu.addAction("Remove Shelf")
            act = menu.exec(QCursor.pos())
            if act in [p_all, p_rnd]:
                vids = [str(x.as_posix()) for x in Path(p).rglob("*") if x.suffix.lower() in ('.mp4','.mkv','.avi')]
                if act == p_rnd: random.shuffle(vids)
                else: vids.sort(key=nat_sort)
                for v in vids:
                    pts = Path(v).parts
                    info = f"{pts[-3]} | {pts[-2]} | {pts[-1]}" if len(pts) >= 3 else Path(v).name
                    li = QListWidgetItem(info); li.setData(Qt.UserRole, v); self.plist.addItem(li)
            elif act == rem:
                self.cfg["folders"].remove(Path(p).as_posix()); config.save(self.cfg); self.ref()
    def p_m(self, p): self.ov.hide(); self.backend.stop_prev(); self.backend.open_main(p)
    def upd(self):
        m_pos = self.tree.viewport().mapFromGlobal(QCursor.pos())
        if self.ov.isVisible() and not self.tree.viewport().rect().contains(m_pos): self.ov.hide(); self.backend.stop_prev()
        m = self.backend.main_player; state = self.backend.get_state_safe()
        self.bp.setIcon(self.icns["pause" if state == 3 else "play"])
        if state == 6 and self.plist.count() > 0:
            idx = (self.plist.currentRow() + 1) % self.plist.count()
            self.plist.setCurrentRow(idx); self.p_m(self.plist.currentItem().data(Qt.UserRole))
        d, cur = m.get_length(), m.get_time()
        if d > 0 and not self.sk.isSliderDown(): self.sk.setValue(int((cur/d)*1000))
        if d > 0: self.lbl_t.setText(f"{cur//60000}:{(cur//1000)%60:02} / {d//60000}:{(d//1000)%60:02}")
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value(); p = str(item.data(0, Qt.UserRole))
            if item.data(0, Qt.DecorationRole) is None and not os.path.isdir(p) and p != "None":
                tp = os.path.join(str(ROOT), "resources", "thumbs", f"{get_h(p)}.jpg")
                if os.path.exists(tp): item.setData(0, Qt.DecorationRole, QPixmap(tp))
                else: self.worker.stdin.write(f"{p}|{self.cfg['preview_start']}\n"); self.worker.stdin.flush()
            it += 1
    def closeEvent(self, e): self.worker.terminate(); self.backend.release(); e.accept()
'''

if __name__ == "__main__":
    dl_assets()
    write_f("app/util/config.py", config_py)
    write_f("app/ui/main_window.py", ui_logic)
    print("\n--- PHASE 81 UNIFIED READY. RUN app/main.py ---")