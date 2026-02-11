import os, time, subprocess, hashlib, vlc, sys, threading, random, re, logging, socket
from queue import PriorityQueue
import itertools
import queue
from pathlib import Path
from qtpy.QtWidgets import *
from qtpy.QtCore import *
from qtpy.QtGui import *
import app.util.config as config
from app.ui.library import LibraryDelegate, get_h
import os, sys, logging, time
from pathlib import Path
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
import app.util.config as config
from app.util.logger import setup_app_logger
from app.util.metadata_db import MetadataDB
from app.util.tvmaze_api import TVMazeAPI

logger = setup_app_logger("MAIN_WINDOW")

ROOT = Path(__file__).resolve().parents[2]


class MainWindow(QMainWindow):
    """A stable, simplified MainWindow implementation.

    This provides a usable UI (title, folders/library, central video area,
    and playback controls). It's intentionally smaller than the original but
    safe and consistent so the app can run while we iteratively restore
    advanced features.
    """

    def __init__(self, player=None, backend=None):
        super().__init__()
        self.player = player
        self.backend = backend
        self.cfg = config.load()
        try:
            self.db = MetadataDB()
        except Exception:
            self.db = None
            logger.exception("Failed to open MetadataDB; continuing without DB")

        self.setWindowTitle("Vibe Video Player")
        self.resize(1100, 700)

        # Root layout
        root = QWidget()
        root_l = QVBoxLayout(root)
        root_l.setContentsMargins(0, 0, 0, 0)
        root_l.setSpacing(0)

        # Title
        title_bar = QLabel("Vibe Video Player")
        title_bar.setAlignment(Qt.AlignCenter)
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet("background:#0e0e0e; color: white; font-weight:600; padding:6px;")
        root_l.addWidget(title_bar)

        # Splitter: left sidebar / center
        splitter = QSplitter(Qt.Horizontal)
        root_l.addWidget(splitter, 1)

        # Left sidebar (folders + toggle)
        left = QWidget(); left_l = QVBoxLayout(left); left_l.setContentsMargins(6,6,6,6)
        toggle_l = QHBoxLayout()
        self.btn_folders = QRadioButton("Folders"); self.btn_folders.setChecked(True)
        self.btn_library = QRadioButton("Library")
        toggle_l.addWidget(self.btn_folders); toggle_l.addWidget(self.btn_library); toggle_l.addStretch()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_library)
        toggle_l.addWidget(self.btn_refresh)
        left_l.addLayout(toggle_l)

        # Folder tree
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True)
        left_l.addWidget(self.tree, 1)
        btn_add = QPushButton("Add Folder")
        btn_add.clicked.connect(self.add_folder)
        left_l.addWidget(btn_add)

        splitter.addWidget(left)

        # Center area: video placeholder + library list
        center = QWidget(); center_l = QVBoxLayout(center); center_l.setContentsMargins(6,6,6,6)
        self.video_area = QLabel("No video loaded")
        self.video_area.setAlignment(Qt.AlignCenter)
        self.video_area.setStyleSheet("background:#111; color:#ddd; border-radius:6px;")
        center_l.addWidget(self.video_area, 1)

        self.library_list = QListWidget()
        self.library_list.itemDoubleClicked.connect(self.on_show_double)
        center_l.addWidget(self.library_list, 1)

        splitter.addWidget(center)
        splitter.setSizes([300, 800])

        # Bottom controls
        ctrl = QWidget(); ctrl_l = QHBoxLayout(ctrl); ctrl_l.setContentsMargins(8,6,8,6)
        self.btn_play = QPushButton("Play/Pause")
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_repeat = QPushButton("Repeat: none")
        self.btn_repeat.clicked.connect(self.toggle_repeat)
        self.btn_shuffle = QPushButton("Shuffle: Off")
        self.btn_shuffle.clicked.connect(self.toggle_shuffle)
        ctrl_l.addWidget(self.btn_play)
        ctrl_l.addWidget(self.btn_repeat)
        ctrl_l.addWidget(self.btn_shuffle)
        ctrl_l.addStretch()
        root_l.addWidget(ctrl)

        self.setCentralWidget(root)

        # internal state
        self.repeat_mode = 'none'
        self.shuffle = False

        # populate initial view
        QTimer.singleShot(150, self.ref)

    # -- Folder / Library management
    def ref(self):
        """Refresh both folder tree and library view."""
        self._populate_folders()
        self.populate_library()

    def _populate_folders(self):
        self.tree.clear()
        for f in self.cfg.get('folders', []):
            p = Path(f)
            if not p.exists():
                continue
            it = QTreeWidgetItem(self.tree, [self.cfg.get('nicknames', {}).get(f, p.name)])
            it.setData(0, Qt.UserRole, str(p))
            it.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Add Folder")
        if d:
            d_posix = Path(d).as_posix()
            if d_posix not in self.cfg.get('folders', []):
                self.cfg.setdefault('folders', []).append(d_posix)
                config.save(self.cfg)
                self._populate_folders()

    def refresh_library(self):
        """Scan folders and try to detect TV shows via TVMaze API, then refresh library."""
        logger.info("Refreshing library by scanning folders: %s", self.cfg.get('folders', []))
        for folder in self.cfg.get('folders', []):
            p = Path(folder)
            if not p.exists():
                continue
            for sub in p.iterdir():
                if not sub.is_dir():
                    continue
                detected = TVMazeAPI.auto_detect(sub.name)
                if detected:
                    try:
                        if self.db:
                            self.db.add_show(detected['tvmaze_id'], detected['name'], detected.get('image_url'))
                    except Exception:
                        logger.exception("Failed to add detected show to DB")
        self.populate_library()

    def populate_library(self):
        self.library_list.clear()
        if not self.db:
            return
        try:
            shows = self.db.get_all_shows()
            for s in shows:
                # s columns: id, tvmaze_id, name, image_url, cached_image_path
                name = s[2] if len(s) > 2 else str(s)
                tvmaze_id = s[1] if len(s) > 1 else None
                it = QListWidgetItem(name)
                it.setData(Qt.UserRole, tvmaze_id)
                self.library_list.addItem(it)
        except Exception:
            logger.exception("populate_library failed")

    def on_show_double(self, item):
        tvmaze_id = item.data(Qt.UserRole)
        name = item.text()
        logger.info("Show double-clicked: %s (%s)", name, tvmaze_id)
        # open seasons/episodes dialog (lightweight)
        seasons = TVMazeAPI.get_show_seasons(tvmaze_id) if tvmaze_id else []
        if not seasons:
            QMessageBox.information(self, "No Seasons", f"No seasons found for {name}")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{name} — Seasons & Episodes")
        h = QHBoxLayout(dialog)
        seasons_list = QListWidget(); episodes_list = QListWidget()
        seasons_list.setFixedWidth(180)
        h.addWidget(seasons_list); h.addWidget(episodes_list)
        season_map = {}
        for s in seasons:
            num = s.get('number')
            if num is None:
                continue
            li = QListWidgetItem(f"Season {num}")
            li.setData(Qt.UserRole, num)
            seasons_list.addItem(li)
            season_map[num] = s

        def on_season_clicked(it):
            episodes_list.clear()
            season_num = it.data(Qt.UserRole)
            all_eps = TVMazeAPI.get_show_episodes(tvmaze_id)
            for ep in all_eps:
                if ep.get('season') == season_num:
                    title = ep.get('name') or f"Episode {ep.get('number')}"
                    li = QListWidgetItem(f"E{ep.get('number'):02} — {title}")
                    li.setData(Qt.UserRole, (season_num, ep.get('number')))
                    episodes_list.addItem(li)

        def on_episode_activated(li):
            if not li:
                return
            season_num, ep_num = li.data(Qt.UserRole)
            # try DB lookup
            if self.db:
                vids = self.db.get_videos_for_episode(tvmaze_id, season_num, ep_num)
                if vids:
                    path = vids[0][1]
                    logger.info("Playing from DB: %s", path)
                    self._play_path(path)
                    dialog.accept(); return
            # not found
            QMessageBox.information(self, "Not Found", f"No local file found for {name} S{season_num:02}E{ep_num:02}")

        seasons_list.itemClicked.connect(lambda it: on_season_clicked(it))
        episodes_list.itemDoubleClicked.connect(lambda it: on_episode_activated(it))
        dialog.exec_()

    # -- Playback helpers
    def _play_path(self, p):
        try:
            if self.backend:
                self.backend.open_main(p)
            self.video_area.setText(Path(p).name)
        except Exception:
            logger.exception("Failed to play %s", p)

    def toggle_play(self):
        try:
            if self.backend and hasattr(self.backend, 'main_player'):
                self.backend.main_player.pause()
        except Exception:
            logger.exception("toggle_play failed")

    def toggle_repeat(self):
        modes = ['none', 'one', 'all']
        idx = modes.index(self.repeat_mode)
        self.repeat_mode = modes[(idx + 1) % len(modes)]
        self.btn_repeat.setText(f"Repeat: {self.repeat_mode}")

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.btn_shuffle.setText(f"Shuffle: {'On' if self.shuffle else 'Off'}")


# End of file
        return super().resizeEvent(e)

    def keyPressEvent(self, event):
        try:
            key = event.key()
            if key == Qt.Key_Space or key == Qt.Key_MediaPlay or key == Qt.Key_MediaPause:
                # Play/Pause
                self.backend.main_player.pause()
            elif key == Qt.Key_Left or key == Qt.Key_MediaPrevious:
                # Seek backward 10s or previous track
                if event.modifiers() & Qt.ControlModifier:
                    # Ctrl+Left: previous track
                    if self.plist.count() > 0:
                        idx = (self.plist.currentRow() - 1) % self.plist.count()
                        self.plist.setCurrentRow(idx)
                        self.p_m(self.plist.currentItem().data(Qt.UserRole))
                else:
                    pos = self.backend.main_player.get_time() - 10000
                    self.backend.main_player.set_time(max(0, pos))
            elif key == Qt.Key_Right or key == Qt.Key_MediaNext:
                # Seek forward 10s or next track
                if event.modifiers() & Qt.ControlModifier:
                    # Ctrl+Right: next track
                    self.play_next()
                else:
                    pos = self.backend.main_player.get_time() + 10000
                    length = self.backend.main_player.get_length()
                    self.backend.main_player.set_time(min(length, pos))
            elif key == Qt.Key_Up or key == Qt.Key_VolumeUp:
                # Volume up
                vol = min(100, self.cfg["volume"] + 5)
                self.set_vol_save(vol)
            elif key == Qt.Key_Down or key == Qt.Key_VolumeDown:
                # Volume down
                vol = max(0, self.cfg["volume"] - 5)
                self.set_vol_save(vol)
            elif key == Qt.Key_F:
                # Toggle fullscreen
                self.toggle_fs()
            elif key == Qt.Key_Escape or key == Qt.Key_Back:
                # Exit fullscreen or back
                if self.isFullScreen():
                    self.showNormal()
                else:
                    # Back navigation: perhaps hide sidebars or something
                    pass
            elif key == Qt.Key_N or key == Qt.Key_MediaNext:
                # Next track
                self.play_next()
            elif key == Qt.Key_P or key == Qt.Key_MediaPrevious:
                # Previous track
                if self.plist.count() > 0:
                    idx = (self.plist.currentRow() - 1) % self.plist.count()
                    self.plist.setCurrentRow(idx)
                    self.p_m(self.plist.currentItem().data(Qt.UserRole))
            elif key == Qt.Key_R:
                # Toggle repeat
                self.toggle_repeat()
            elif key == Qt.Key_S:
                # Toggle shuffle
                self.toggle_shuffle()
            elif key == Qt.Key_M or key == Qt.Key_VolumeMute:
                # Mute/unmute
                if self.cfg["volume"] > 0:
                    self._last_vol = self.cfg["volume"]
                    self.set_vol_save(0)
                else:
                    self.set_vol_save(self._last_vol if hasattr(self, '_last_vol') else 50)
            elif key == Qt.Key_Backspace:
                # Back button
                if self.isFullScreen():
                    self.showNormal()
                elif self.sb_l.isVisible():
                    self.sb_l.hide()
                elif self.sb_r.isVisible():
                    self.sb_r.hide()
                else:
                    # Perhaps close or something
                    pass
            else:
                super().keyPressEvent(event)
        except Exception:
            logger.exception("Error handling key press")
            super().keyPressEvent(event)

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
        if p:
            p_posix = Path(p).as_posix()
            if p_posix not in self.cfg["folders"]: self.cfg["folders"].append(p_posix); config.save(self.cfg); self.ref()
    def ref_initial(self): self.split.setSizes([self.cfg["sidebar_width"], 800, 300]); self.ref()
    def ref(self):
        self.tree.clear()
        for f in self.cfg["folders"]:
            p = Path(f)
            if p.exists():
                it = QTreeWidgetItem(self.tree, [self.cfg["nicknames"].get(f, p.name)])
                it.setIcon(0, self.icns["folder"]); it.setData(0, Qt.UserRole, f); it.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
        self.populate_library()
    def on_expand(self, item):
        if item.childCount() > 0: return
        p = Path(item.data(0, Qt.UserRole))
        try:
            for e in sorted(p.iterdir()):
                if e.is_dir():
                    n = self.cfg["nicknames"].get(e.as_posix(), e.name)
                    c = QTreeWidgetItem(item, [n]); c.setIcon(0, self.icns["folder"]); c.setData(0, Qt.UserRole, e.as_posix()); c.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                elif e.suffix.lower() in ('.mp4','.mkv','.avi'):
                    v = QTreeWidgetItem(item, [e.name]); v.setData(0, Qt.UserRole, e.as_posix())
                    v.setFlags(v.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable); v.setCheckState(0, Qt.Unchecked)
        except Exception:
            logger.exception("Error expanding folder %s", p)
        # Try to detect if this folder is a TV show
        if not item.parent():  # root level
            detected = TVMazeAPI.auto_detect(p.name)
            if detected:
                self.db.add_show(detected['tvmaze_id'], detected['name'], detected['image_url'])
                cache_dir = Path(ROOT) / "resources" / "thumbs"
                cache_dir.mkdir(exist_ok=True)
                cache_path = cache_dir / f"show_{detected['tvmaze_id']}.jpg"
                if not cache_path.exists() and detected['image_url']:
                    if TVMazeAPI.download_image(detected['image_url'], str(cache_path)):
                        self.db.update_show_cached_image(detected['tvmaze_id'], str(cache_path))
                        # Update item icon
                        pixmap = QPixmap(str(cache_path))
                        if not pixmap.isNull():
                            item.setIcon(0, QIcon(pixmap.scaled(32, 32, Qt.KeepAspectRatio)))
    def on_tree_click(self, it, col):
        p = it.data(0, Qt.UserRole)
        if p and not os.path.isdir(p) and self.tree.viewport().mapFromGlobal(QCursor.pos()).x() < 30:
            if p in self.checked_paths: self.checked_paths.remove(p)
            else: self.checked_paths.add(p)
            self.tree.viewport().update()
    def on_hover(self, it, col):
        p = it.data(0, Qt.UserRole)
        if self.cfg["show_video"] and p and not os.path.isdir(p):
            # Removed video preview; only keep for potential tooltips or selection
            pass
        else:
            pass
        # Keep hover for selection if needed
        self._hover_preview = p
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
                self.checked_paths.clear(); self.tree.viewport().update(); self.sort_pl()
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
                self.sort_pl()
            elif act == rem: self.rem_fld(p)
    def rem_fld(self, p):
        p_posix = Path(p).as_posix()
        if p_posix in self.cfg["folders"]: self.cfg["folders"].remove(p_posix); config.save(self.cfg); self.ref()
    def sort_pl(self):
        items = []
        for i in range(self.plist.count()):
            it = self.plist.item(i); items.append({'i': it.text(), 'p': it.data(Qt.UserRole)})
        items.sort(key=lambda x: nat_sort(x['p'])); self.plist.clear()
        for x in items:
            li = QListWidgetItem(x['i'])
            li.setData(Qt.UserRole, x['p'])
            self.plist.addItem(li)
    def p_m(self, p): 
        self.ov.hide(); self.backend.stop_prev(); self.backend.open_main(p)
        for i in range(self.plist.count()):
            if self.plist.item(i).data(Qt.UserRole) == p: self.plist.setCurrentRow(i); break
        try:
            self._now_playing = p
            try:
                if hasattr(self, '_title_bar') and self._title_bar is not None:
                    # set centered title via helper
                    self._title_bar.setTitle(Path(p).name)
            except Exception:
                logger.exception("Failed to set title in title bar for %s", p)
        except Exception:
            logger.exception("Error handling play metadata for %s", p)
    def toggle_repeat(self):
        modes = ['none', 'one', 'all']
        current_idx = modes.index(self.repeat_mode)
        self.repeat_mode = modes[(current_idx + 1) % len(modes)]
        self.bt_repeat.setText(f"Repeat {self.repeat_mode.title()}")

    def switch_view(self, button):
        idx = self.view_toggle.id(button)
        self.view_stack.setCurrentIndex(idx)
        if idx == 1:  # Library view
            self.populate_library()
        

    def refresh_library(self):
        logger.info("Refreshing library by scanning folders: %s", self.cfg.get("folders", []))
        # Scan folders for potential TV shows and update DB
        for folder in self.cfg["folders"]:
            p = Path(folder)
            logger.debug("Scanning folder %s", p)
            if p.exists():
                for subdir in p.iterdir():
                    if subdir.is_dir():
                        logger.debug("Checking subdir %s for show detection", subdir)
                        detected = TVMazeAPI.auto_detect(subdir.name)
                        if detected:
                            logger.info("Detected show: %s -> %s", subdir, detected)
                            self.db.add_show(detected['tvmaze_id'], detected['name'], detected['image_url'])
                            cache_dir = Path(ROOT) / "resources" / "thumbs"
                            cache_dir.mkdir(exist_ok=True)
                            cache_path = cache_dir / f"show_{detected['tvmaze_id']}.jpg"
                            if not cache_path.exists() and detected['image_url']:
                                if TVMazeAPI.download_image(detected['image_url'], str(cache_path)):
                                    self.db.update_show_cached_image(detected['tvmaze_id'], str(cache_path))
        self.populate_library()

    def on_show_selected(self, item):
        tvmaze_id = item.data(Qt.UserRole)
        show_name = item.text()
        seasons = TVMazeAPI.get_show_seasons(tvmaze_id)
        if not seasons:
            logger.info(f"No seasons found for {show_name}")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{show_name} — Seasons & Episodes")
        dlg_lay = QHBoxLayout(dialog)

        seasons_list = QListWidget()
        episodes_list = QListWidget()
        seasons_list.setFixedWidth(180)
        dlg_lay.addWidget(seasons_list)
        dlg_lay.addWidget(episodes_list)

        # populate seasons
        season_map = {}
        for s in seasons:
            num = s.get('number')
            if num is None:
                continue
            si = QListWidgetItem(f"Season {num}")
            si.setData(Qt.UserRole, num)
            seasons_list.addItem(si)
            season_map[num] = s

        def on_season_clicked(it):
            episodes_list.clear()
            season_num = it.data(Qt.UserRole)
            all_eps = TVMazeAPI.get_show_episodes(tvmaze_id)
            for ep in all_eps:
                if ep.get('season') == season_num:
                    title = ep.get('name') or f"Episode {ep.get('number')}"
                    li = QListWidgetItem(f"E{ep.get('number'):02} — {title}")
                    li.setData(Qt.UserRole, (season_num, ep.get('number')))
                    episodes_list.addItem(li)

        def on_episode_activated(li):
            if not li: return
            season_num, ep_num = li.data(Qt.UserRole)
            # Try DB lookup first
            vids = self.db.get_videos_for_episode(tvmaze_id, season_num, ep_num)
            if vids and len(vids) > 0:
                path = vids[0][1]  # path is second column in videos table
                self.p_m(path)
                dialog.accept()
                return
            # Otherwise scan folders for matching file
            found = self.find_episode_file(tvmaze_id, season_num, ep_num)
            if found:
                # add to DB for future
                self.db.add_video(found, title=Path(found).stem, show_name=show_name, season=season_num, episode=ep_num, tvmaze_id=tvmaze_id)
                self.p_m(found)
                dialog.accept()
                return
            QMessageBox.information(self, "Not Found", f"No local file found for {show_name} S{season_num:02}E{ep_num:02}")

        seasons_list.itemClicked.connect(lambda it: on_season_clicked(it))
        episodes_list.itemDoubleClicked.connect(lambda it: on_episode_activated(it))

        dialog.exec_()

    def play_next(self):
        if self.plist.count() == 0: return
        if self.repeat_mode == 'one':
            # Repeat current
            self.p_m(self.plist.currentItem().data(Qt.UserRole))
            return
        idx = self.plist.currentRow()
        if self.shuffle:
            idx = random.randint(0, self.plist.count() - 1)
        else:
            idx = (idx + 1) % self.plist.count()
        self.plist.setCurrentRow(idx); self.p_m(self.plist.currentItem().data(Qt.UserRole))
    def find_episode_file(self, tvmaze_id, season, episode):
        logger.debug("Searching for episode file: tvmaze=%s S=%s E=%s", tvmaze_id, season, episode)
        # more flexible pattern: S01E01 or S1E1
        flexible = re.compile(r'[Ss](?P<s>\d{1,2})[\W_]*[Ee](?P<e>\d{1,3})')
        for folder in self.cfg.get("folders", []):
            p = Path(folder)
            logger.debug("Scanning folder for episodes: %s", p)
            if not p.exists():
                logger.debug("Folder does not exist: %s", p)
                continue
            try:
                for f in p.rglob('*'):
                    if not f.is_file():
                        continue
                    if f.suffix.lower() not in ('.mp4', '.mkv', '.avi'):
                        continue
                    name = f.name
                    m = flexible.search(name)
                    if m:
                        s = int(m.group('s'))
                        e = int(m.group('e'))
                        if s == season and e == episode:
                            logger.info("Matched episode file: %s", f)
                            return str(f.as_posix())
            except Exception:
                logger.exception("Error scanning folder %s for episodes", folder)
        logger.debug("No episode file found for tvmaze=%s S=%s E=%s", tvmaze_id, season, episode)
        return None
    def upd(self):
        m_pos = self.tree.viewport().mapFromGlobal(QCursor.pos())
        if self.ov.isVisible() and not self.tree.viewport().rect().contains(m_pos): self.ov.hide(); self.backend.stop_prev()
        m = self.backend.main_player; state = self.backend.get_state_safe()
        self.bp.setIcon(self.icns["pause" if state == 3 else "play"])
        if state == 6 and self.plist.count() > 0 and self.repeat_mode != 'none': self.play_next()
        d, cur = m.get_length(), m.get_time()
        if d > 0 and not self.sk.isSliderDown(): self.sk.setValue(int((cur/d)*1000))
        if d > 0: self.lbl_t.setText(f"{cur//60000}:{(cur//1000)%60:02} / {d//60000}:{(d//1000)%60:02}")
        it = QTreeWidgetItemIterator(self.tree)
        while it.value():
            item = it.value(); p = str(item.data(0, Qt.UserRole))
            if item.data(0, Qt.DecorationRole) is None and not os.path.isdir(p) and p != "None":
                tp = os.path.join(str(ROOT), "resources", "thumbs", f"{get_h(p)}.jpg")
                if os.path.exists(tp):
                    item.setData(0, Qt.DecorationRole, QPixmap(tp))
                else:
                    try:
                        # Ensure worker is alive before writing
                        self._ensure_worker_running()
                        # Log diagnostics about the worker and stdin before attempting write
                        try:
                            wpid = getattr(self.worker, 'pid', None)
                            wpoll = None if self.worker is None else self.worker.poll()
                            ipc_port = getattr(self, '_ipc_port', None)
                            logger.debug("Attempting to request thumbnail: pid=%s poll=%s ipc_port=%s p=%s", wpid, wpoll, ipc_port, p)
                            if ipc_port:
                                logger.debug("Worker IPC port: %s", ipc_port)
                        except Exception:
                            logger.exception("Failed to collect worker diagnostics before write")

                        # Enqueue the thumbnail request for the writer thread to handle
                        try:
                            try:
                                self._ensure_worker_running()
                            except Exception:
                                logger.exception("Failed to ensure worker before enqueue")
                            try:
                                # Deduplicate: skip if a request for this path is already pending
                                if p in self._pending_thumbs:
                                    logger.debug("Thumbnail request already pending for %s; skipping enqueue", p)
                                else:
                                    # Prioritize the currently-hovered preview path
                                    pri = 0 if getattr(self, '_hover_preview', None) == p else 1
                                    seq = next(self._seq)
                                    try:
                                        self._thumb_queue.put_nowait((pri, seq, (p, self.cfg['preview_start'])))
                                        self._pending_thumbs.add(p)
                                        self._metrics['queued'] += 1
                                        logger.debug("Enqueued thumbnail request for %s (pri=%s)", p, pri)
                                    except queue.Full:
                                        self._metrics['dropped'] += 1
                                        logger.warning("Thumbnail queue full; dropping request for %s", p)
                                    except Exception:
                                        logger.exception("Failed to enqueue thumbnail request for %s", p)
                            except Exception:
                                logger.exception("Unexpected error while enqueuing thumbnail for %s", p)
                        except Exception:
                            logger.exception("Unexpected error while enqueuing thumbnail for %s", p)
                    except Exception:
                        logger.exception("Failed to request thumbnail for %s", p)
            it += 1
    def toggle_repeat(self):
        modes = ['none', 'one', 'all']
        current_idx = modes.index(self.repeat_mode)
        self.repeat_mode = modes[(current_idx + 1) % len(modes)]
        self.bt_repeat.setText(f"Repeat {self.repeat_mode.title()}")

    def _monitor_controller(self):
        try:
            while True:
                events = inputs.get_gamepad()
                for event in events:
                    if event.state == 1:  # Button press
                        if event.code == 'BTN_SOUTH':  # A / Cross
                            self.backend.main_player.pause()
                        elif event.code == 'BTN_EAST':  # B / Circle
                            self.play_next()
                        elif event.code == 'BTN_WEST':  # X / Square
                            if self.plist.count() > 0:
                                idx = (self.plist.currentRow() - 1) % self.plist.count()
                                self.plist.setCurrentRow(idx)
                                self.p_m(self.plist.currentItem().data(Qt.UserRole))
                        elif event.code == 'BTN_NORTH':  # Y / Triangle
                            self.toggle_fs()
                        elif event.code == 'BTN_SELECT':  # Select
                            self.toggle_repeat()
                        elif event.code == 'BTN_START':  # Start
                            self.toggle_shuffle()
                        elif event.code == 'ABS_Y-':  # D-pad up
                            vol = min(100, self.cfg["volume"] + 5)
                            self.set_vol_save(vol)
                        elif event.code == 'ABS_Y+':  # D-pad down
                            vol = max(0, self.cfg["volume"] - 5)
                            self.set_vol_save(vol)
                        elif event.code == 'ABS_X-':  # D-pad left
                            pos = self.backend.main_player.get_time() - 10000
                            self.backend.main_player.set_time(max(0, pos))
                        elif event.code == 'ABS_X+':  # D-pad right
                            pos = self.backend.main_player.get_time() + 10000
                            length = self.backend.main_player.get_length()
                            self.backend.main_player.set_time(min(length, pos))
        except Exception:
            logger.exception("Controller monitoring error")

    def toggle_repeat(self):
        modes = ['none', 'one', 'all']
        current_idx = modes.index(self.repeat_mode)
        self.repeat_mode = modes[(current_idx + 1) % len(modes)]
        self.bt_repeat.setText(f"Repeat {self.repeat_mode.title()}")

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.bt_shuffle.setText("Shuffle On" if self.shuffle else "Shuffle Off")

    def play_next(self):
        if self.plist.count() == 0: return
        if self.repeat_mode == 'one':
            # Repeat current
            self.p_m(self.plist.currentItem().data(Qt.UserRole))
            return
        idx = self.plist.currentRow()
        if self.shuffle:
            idx = random.randint(0, self.plist.count() - 1)
        else:
            idx = (idx + 1) % self.plist.count()
        self.plist.setCurrentRow(idx); self.p_m(self.plist.currentItem().data(Qt.UserRole))
    def closeEvent(self, e):
        try:
            # Signal writer thread to exit using a sentinel tuple
            try:
                seq = next(self._seq)
                self._thumb_queue.put_nowait((999999, seq, None))
            except Exception:
                pass
        except Exception:
            logger.exception("Error signaling writer thread to stop")
        try:
            if self.worker:
                try:
                    self.worker.terminate()
                except Exception:
                    logger.exception("Failed to terminate worker")
        except Exception:
            logger.exception("Error while terminating worker on close")
        try:
            self.backend.release()
        except Exception:
            logger.exception("Error releasing backend on close")
        e.accept()


# Minimal MainWindow fallback to allow importing when the full UI is corrupted.
# This provides a lightweight window so the app can start and the user can continue.
class MinimalMainWindow(QMainWindow):
    def __init__(self, player=None, backend=None):
        super().__init__()
        self.player = player
        self.backend = backend
        self.setWindowTitle("Vibe Video Player (Minimal)")
        self.resize(1000, 700)
        try:
            w = QLabel("Minimal MainWindow — UI partially unavailable.\nSee logs for details.")
            w.setAlignment(Qt.AlignCenter)
            self.setCentralWidget(w)
        except Exception:
            pass


# Lightweight functional MainWindow to use while full UI is being restored.
class MainWindow(QMainWindow):
    def __init__(self, player=None, backend=None):
        super().__init__()
        self.player = player
        self.backend = backend
        self.cfg = config.load()
        try:
            self.db = MetadataDB()
        except Exception:
            self.db = None
        self.setWindowTitle("Vibe Video Player")
        self.resize(1000, 700)

        # Simple layout: title, library, controls
        root = QWidget(); root_l = QVBoxLayout(root); root_l.setContentsMargins(8,8,8,8)
        self.title_lbl = QLabel("Vibe Video Player")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        root_l.addWidget(self.title_lbl)

        self.library_list = QListWidget()
        self.library_list.itemDoubleClicked.connect(self._on_item_activated)
        root_l.addWidget(self.library_list, 1)

        ctrl_row = QHBoxLayout()
        self.bp = QPushButton("Play/Pause"); self.bp.clicked.connect(self.toggle_play)
        self.bt_repeat = QPushButton("Repeat"); self.bt_repeat.clicked.connect(self.toggle_repeat)
        self.bt_shuffle = QPushButton("Shuffle"); self.bt_shuffle.clicked.connect(self.toggle_shuffle)
        ctrl_row.addWidget(self.bp); ctrl_row.addWidget(self.bt_repeat); ctrl_row.addWidget(self.bt_shuffle)
        root_l.addLayout(ctrl_row)

        self.setCentralWidget(root)

        # Modes
        self.repeat_mode = 'none'
        self.shuffle = False

        # Populate library from DB if available
        QTimer.singleShot(100, self.populate_library)

    def populate_library(self):
        self.library_list.clear()
        if not self.db:
            return
        try:
            shows = self.db.get_all_shows()
            for s in shows:
                # shows rows: id, tvmaze_id, name, image_url, cached_image_path
                name = s[2] if len(s) > 2 else str(s)
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, s[1] if len(s) > 1 else None)
                self.library_list.addItem(item)
        except Exception:
            logger.exception("Failed to populate library")

    def refresh_library(self):
        # simple alias for populate
        self.populate_library()

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.bt_shuffle.setText(f"Shuffle ({'On' if self.shuffle else 'Off'})")

    def toggle_repeat(self):
        modes = ['none', 'one', 'all']
        idx = modes.index(self.repeat_mode)
        self.repeat_mode = modes[(idx + 1) % len(modes)]
        self.bt_repeat.setText(f"Repeat: {self.repeat_mode}")

    def toggle_play(self):
        try:
            if self.backend and hasattr(self.backend, 'main_player'):
                self.backend.main_player.pause()
        except Exception:
            logger.exception("Failed to toggle play")

    def _on_item_activated(self, item):
        tvid = item.data(Qt.UserRole)
        # placeholder: log selection
        logger.info("Selected show from simple UI: %s (tvmaze=%s)", item.text(), tvid)