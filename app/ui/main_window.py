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
from app.util.logger import setup_app_logger
from app.util.metadata_db import MetadataDB
from app.util.tvmaze_api import TVMazeAPI
try:
    import inputs
    INPUTS_AVAILABLE = True
except ImportError:
    INPUTS_AVAILABLE = False

logger = setup_app_logger("MAIN_WINDOW")

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

class TitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._window = parent
        self.setFixedHeight(34)
        self.setObjectName("title_bar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6,0,6,0)
        lay.setSpacing(6)
        self.icon_lbl = QLabel(); self.icon_lbl.setFixedSize(20,20)
        # Title label starts empty; main window will populate with current media title
        self.title_lbl = QLabel("")
        self.title_lbl.setStyleSheet("font-weight:600; color: white; background: transparent;")
        self.title_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.icon_lbl)
        # center the title by sandwiching it between stretches
        lay.addStretch()
        lay.addWidget(self.title_lbl, 1)
        lay.addStretch()
        self.btn_min = QPushButton(); self.btn_min.setFixedSize(28,20)
        self.btn_max = QPushButton(); self.btn_max.setFixedSize(28,20)
        self.btn_close = QPushButton(); self.btn_close.setFixedSize(28,20)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet("background:transparent; color:white; border:none;")
        # Use platform style icons for titlebar controls for better appearance
        try:
            self.btn_min.setIcon(self.style().standardIcon(QStyle.SP_TitleBarMinButton))
            self.btn_max.setIcon(self.style().standardIcon(QStyle.SP_TitleBarMaxButton))
            self.btn_close.setIcon(self.style().standardIcon(QStyle.SP_TitleBarCloseButton))
        except Exception:
            # fall back to text glyphs
            self.btn_min.setText("—"); self.btn_max.setText("▢"); self.btn_close.setText("✕")
        lay.addWidget(self.btn_min); lay.addWidget(self.btn_max); lay.addWidget(self.btn_close)
        if self._window is not None:
            self.btn_min.clicked.connect(self._window.showMinimized)
            self.btn_max.clicked.connect(self._toggle_max_restore)
            self.btn_close.clicked.connect(self._window.close)
        self._drag_pos = None

    def _toggle_max_restore(self):
        try:
            if not hasattr(self._window, '_normal_geom'):
                self._window._normal_geom = None
            if self._window.isMaximized():
                # restore to previous normal geometry if known
                self._window.showNormal()
                if getattr(self._window, '_normal_geom', None) is not None:
                    # apply geometry after the window state change
                    QTimer.singleShot(0, lambda: self._window.setGeometry(self._window._normal_geom))
            else:
                # save current geometry then maximize
                try:
                    self._window._normal_geom = self._window.geometry()
                except Exception:
                    self._window._normal_geom = None
                self._window.showMaximized()
        except Exception:
            logger.exception("Error toggling maximize/restore")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_pos and self._window and not self._window.isMaximized():
            delta = e.globalPosition().toPoint() - self._drag_pos
            self._window.move(self._window.pos() + delta)
            self._drag_pos = e.globalPosition().toPoint()
        super().mouseMoveEvent(e)

    def _update_max_icon(self):
        try:
            if self._window.isMaximized():
                try:
                    self.btn_max.setIcon(self.style().standardIcon(QStyle.SP_TitleBarNormalButton))
                except Exception:
                    self.btn_max.setText("❐")
            else:
                try:
                    self.btn_max.setIcon(self.style().standardIcon(QStyle.SP_TitleBarMaxButton))
                except Exception:
                    self.btn_max.setText("▢")
        except Exception:
            pass

    # ensure title is centered visually by constraining its elide behaviour
    def setTitle(self, text):
        try:
            self.title_lbl.setText(text)
        except Exception:
            pass


class MainWindow(QMainWindow):
    def __init__(self, player, backend):
        super().__init__(); self.player, self.backend = player, backend
        # Use frameless window and provide custom hit-testing/resize handles
        try:
            flags = Qt.Window | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint
            self.setWindowFlags(flags)
        except Exception:
            pass
        self.cfg = config.load(); self.checked_paths = set()
        self.setWindowTitle("Vibe Video Player"); self.resize(1600, 900)
        self.setStyleSheet("background:#0a0a0a; color:white;"); self.setMouseTracking(True)
        self.db = MetadataDB()
        def icn(k): return QIcon(str(ROOT / "resources" / "icons" / f"{k}.png"))
        self.icns = {k: icn(k) for k in ["play","pause","playlist","folder","settings"]}
        # Load the main app icon (prefer generated sizes) and set window icon
        try:
            main_icon_path = ROOT / "resources" / "icons" / "sizes" / "main-64.png"
            if not main_icon_path.exists():
                main_icon_path = ROOT / "resources" / "icons" / "main.png"
            if main_icon_path.exists():
                try:
                    main_qicon = QIcon(str(main_icon_path))
                    self.setWindowIcon(main_qicon)
                    self.icns['main'] = main_qicon
                except Exception:
                    logger.exception("Failed to set window icon from %s", main_icon_path)
        except Exception:
            logger.exception("Failed to initialize main icon")
        # Start the thumbnail worker as a subprocess. On Windows, hide the console window.
        self.worker = None
        def _make_startupinfo():
            si = None
            if sys.platform.startswith("win"):
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                except Exception:
                    logger.exception("Failed to configure subprocess STARTUPINFO")
                    si = None
            return si

        # Track last start time to avoid rapid restart loops
        self._last_worker_start = 0

        def start_worker():
            # Avoid restarting more than once per second
            if time.time() - self._last_worker_start < 1:
                logger.info("Skipping worker restart due to backoff")
                return None
            si = _make_startupinfo()
            try:
                # Choose an IPC port for the worker to listen on
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
                s.close()
                self._ipc_port = port
                # Start worker with ipc port argument. Capture stdout/stderr so we can pipe worker logs into the main logger.
                proc = subprocess.Popen([
                    sys.executable, str(ROOT / "app" / "util" / "worker.py"), f"--ipc-port={port}"
                ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0, startupinfo=si)
                self._last_worker_start = time.time()
                try:
                    logger.info("Started worker pid=%s stdout=%s stderr=%s cwd=%s", proc.pid, bool(proc.stdout), bool(proc.stderr), os.getcwd())
                except Exception:
                    logger.exception("Started worker but failed to log details")
                # worker will accept socket connections on the assigned port; we'll connect in the writer thread
                return proc
            except Exception:
                logger.exception("Failed to start worker subprocess")
                return None

        # start the worker and store reference
        self.worker = start_worker()

        # If the worker provides stdout/stderr, start threads to forward them to app logger
        def _drain_pipe(pipe, level=logging.INFO):
            try:
                if pipe is None:
                    return
                # read bytes and decode lines
                with pipe:
                    buf = b''
                    while True:
                        chunk = pipe.readline()
                        if not chunk:
                            break
                        try:
                            line = chunk.decode('utf-8', errors='replace').rstrip('\r\n')
                        except Exception:
                            line = str(chunk)
                        logger.log(level, "[worker] %s", line)
            except Exception:
                logger.exception("Error reading worker pipe")

        if self.worker is not None:
            if getattr(self.worker, 'stdout', None):
                threading.Thread(target=_drain_pipe, args=(self.worker.stdout, logging.INFO), daemon=True).start()
            if getattr(self.worker, 'stderr', None):
                threading.Thread(target=_drain_pipe, args=(self.worker.stderr, logging.ERROR), daemon=True).start()

        def ensure_worker_running():
            if self.worker is None:
                logger.info("Worker missing, starting")
                self.worker = start_worker()
                # attach drains for new worker
                if self.worker is not None:
                    if getattr(self.worker, 'stdout', None):
                        threading.Thread(target=_drain_pipe, args=(self.worker.stdout, logging.INFO), daemon=True).start()
                    if getattr(self.worker, 'stderr', None):
                        threading.Thread(target=_drain_pipe, args=(self.worker.stderr, logging.ERROR), daemon=True).start()
                return

            if self.worker.poll() is not None:
                # process has exited; capture any remaining stderr/stdout
                try:
                    out = None
                    err = None
                    try:
                        if getattr(self.worker, 'stdout', None):
                            out = self.worker.stdout.read()
                    except Exception:
                        out = None
                    try:
                        if getattr(self.worker, 'stderr', None):
                            err = self.worker.stderr.read()
                    except Exception:
                        err = None
                    if out:
                        try:
                            logger.info("Worker stdout on exit: %s", out.decode('utf-8', errors='replace'))
                        except Exception:
                            logger.info("Worker stdout on exit: %s", out)
                    if err:
                        try:
                            logger.error("Worker stderr on exit: %s", err.decode('utf-8', errors='replace'))
                        except Exception:
                            logger.error("Worker stderr on exit: %s", err)
                except Exception:
                    logger.exception("Error while reading worker pipes on exit")
                logger.info("Worker not running, restarting")
                self.worker = start_worker()
                if self.worker is not None:
                    if getattr(self.worker, 'stdout', None):
                        threading.Thread(target=_drain_pipe, args=(self.worker.stdout, logging.INFO), daemon=True).start()
                    if getattr(self.worker, 'stderr', None):
                        threading.Thread(target=_drain_pipe, args=(self.worker.stderr, logging.ERROR), daemon=True).start()

        self._start_worker = start_worker
        self._ensure_worker_running = ensure_worker_running
        # Prioritized queue + socket-based writer thread to serialize thumbnail requests off the UI thread
        # PriorityQueue entries: (priority, seq, (path, preview)) where lower priority value => higher priority
        self._thumb_queue = PriorityQueue(maxsize=200)
        self._pending_thumbs = set()
        self._seq = itertools.count()
        # Metrics
        self._metrics = {
            'queued': 0,
            'dropped': 0,
            'sent': 0,
            'send_fail': 0,
            'conn_attempts': 0,
            'conn_success': 0,
        }

        def _thumb_writer():
            sock = None
            last_port = None
            while True:
                try:
                    item = self._thumb_queue.get()
                    if item is None:
                        break
                    # item is (priority, seq, payload)
                    if isinstance(item, tuple) and len(item) == 3:
                        pri, seq, payload = item
                    else:
                        # unexpected sentinel/payload
                        break
                    # Accept a None payload as the shutdown sentinel
                    if payload is None:
                        try:
                            self._thumb_queue.task_done()
                        except Exception:
                            pass
                        break
                    p, preview = payload
                    try:
                        # Ensure a current worker/process exists; if not, try to start one
                        try:
                            self._ensure_worker_running()
                        except Exception:
                            logger.exception("Failed to ensure worker before writer socket send")

                        port = getattr(self, '_ipc_port', None)
                        # If port changed or socket not connected, (re)connect
                        if sock is None or last_port != port:
                            if sock:
                                try:
                                    sock.close()
                                except Exception:
                                    pass
                                sock = None
                            if not port:
                                # No port assigned; back off and requeue
                                try:
                                    time.sleep(0.1)
                                    self._thumb_queue.put_nowait((pri, seq, (p, preview)))
                                except Exception:
                                    logger.debug("Failed to requeue while waiting for port: %s", p)
                                continue
                            # Attempt to connect with backoff
                            connected = False
                            conn_backoff = 0.1
                            while not connected:
                                try:
                                    self._metrics['conn_attempts'] += 1
                                    sock = socket.create_connection(('127.0.0.1', port), timeout=3)
                                    last_port = port
                                    connected = True
                                    self._metrics['conn_success'] += 1
                                    conn_backoff = 0.1
                                except Exception:
                                    logger.debug("Socket connect failed to port %s; backing off %.1fs", port, conn_backoff)
                                    time.sleep(conn_backoff)
                                    conn_backoff = min(conn_backoff * 2, 5.0)

                        # send payload
                        try:
                            msg = f"{p}|{preview}\n".encode('utf-8')
                            sock.sendall(msg)
                            self._metrics['sent'] += 1
                            logger.debug("Socket writer sent %d bytes to %s", len(msg), p)
                        except Exception:
                            logger.exception("Socket send failed for %s", p)
                            self._metrics['send_fail'] += 1
                            try:
                                sock.close()
                            except Exception:
                                pass
                            sock = None
                            # Requeue with backoff
                            try:
                                time.sleep(0.1)
                                self._thumb_queue.put_nowait((pri, seq, (p, preview)))
                            except Exception:
                                logger.debug("Failed to requeue after socket send failure for %s", p)
                    finally:
                        try:
                            self._pending_thumbs.discard(p)
                        except Exception:
                            pass
                        try:
                            self._thumb_queue.task_done()
                        except Exception:
                            pass
                except Exception:
                    logger.exception("Exception in thumb writer loop")
                    time.sleep(0.1)

        threading.Thread(target=_thumb_writer, daemon=True).start()
        # Periodic metrics logger to observe queue/connection health
        try:
            self._metrics_timer = QTimer()
            self._metrics_timer.setInterval(5000)
            self._metrics_timer.timeout.connect(lambda: logger.info("Thumb metrics: %s", self._metrics))
            self._metrics_timer.start()
        except Exception:
            logger.exception("Failed to start metrics timer")
        cw = QWidget(); self.setCentralWidget(cw)
        root_v = QVBoxLayout(cw); root_v.setContentsMargins(0,0,0,0); root_v.setSpacing(0)
        # custom title bar
        try:
            self._title_bar = TitleBar(self)
            # set icon if available
            try:
                if 'main' in self.icns:
                    pm = self.icns['main'].pixmap(20,20)
                    self._title_bar.icon_lbl.setPixmap(pm)
            except Exception:
                logger.exception("Failed to set title bar icon pixmap")
            self._title_bar.setStyleSheet('background:#0e0e0e;')
            root_v.addWidget(self._title_bar)
            try:
                self._title_bar._update_max_icon()
            except Exception:
                pass
        except Exception:
            logger.exception("Failed to create custom title bar")
        # create resize handles (frameless windows need custom resizing)
        try:
            class ResizeHandle(QWidget):
                def __init__(self, parent, pos):
                    super().__init__(parent)
                    self._pos = pos
                    self._pressed = False
                    self._start_geo = None
                    self._start_pt = None
                    curs = Qt.ArrowCursor
                    if pos in ('left','right'):
                        curs = Qt.SizeHorCursor
                    elif pos in ('top','bottom'):
                        curs = Qt.SizeVerCursor
                    elif pos in ('topleft','bottomright'):
                        curs = Qt.SizeFDiagCursor
                    elif pos in ('topright','bottomleft'):
                        curs = Qt.SizeBDiagCursor
                    self.setCursor(curs)
                    self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                def mousePressEvent(self, e):
                    if e.button() == Qt.LeftButton:
                        self._pressed = True
                        self._start_geo = self.parent().geometry()
                        self._start_pt = e.globalPosition().toPoint()
                def mouseMoveEvent(self, e):
                    if not self._pressed: return
                    try:
                        cur = e.globalPosition().toPoint(); dx = cur.x() - self._start_pt.x(); dy = cur.y() - self._start_pt.y()
                        g = self._start_geo
                        x, y, w, h = g.x(), g.y(), g.width(), g.height()
                        min_w, min_h = 320, 180
                        if self._pos == 'left':
                            nx = x + dx; nw = w - dx
                            if nw >= min_w: self.parent().setGeometry(nx, y, nw, h)
                        elif self._pos == 'right':
                            nw = w + dx
                            if nw >= min_w: self.parent().setGeometry(x, y, nw, h)
                        elif self._pos == 'top':
                            ny = y + dy; nh = h - dy
                            if nh >= min_h: self.parent().setGeometry(x, ny, w, nh)
                        elif self._pos == 'bottom':
                            nh = h + dy
                            if nh >= min_h: self.parent().setGeometry(x, y, w, nh)
                        elif self._pos == 'topleft':
                            nx = x + dx; ny = y + dy; nw = w - dx; nh = h - dy
                            if nw >= min_w and nh >= min_h: self.parent().setGeometry(nx, ny, nw, nh)
                        elif self._pos == 'topright':
                            ny = y + dy; nw = w + dx; nh = h - dy
                            if nw >= min_w and nh >= min_h: self.parent().setGeometry(x, ny, nw, nh)
                        elif self._pos == 'bottomleft':
                            nx = x + dx; nw = w - dx; nh = h + dy
                            if nw >= min_w and nh >= min_h: self.parent().setGeometry(nx, y, nw, nh)
                        elif self._pos == 'bottomright':
                            nw = w + dx; nh = h + dy
                            if nw >= min_w and nh >= min_h: self.parent().setGeometry(x, y, nw, nh)
                    except Exception:
                        logger.exception("Resize handle move error")
                def mouseReleaseEvent(self, e):
                    self._pressed = False

            self._resize_handles = {}
            for pos in ('left','right','top','bottom','topleft','topright','bottomleft','bottomright'):
                h = ResizeHandle(self, pos)
                h.setObjectName(f"resize_{pos}")
                h.setFixedSize(8,8)
                h.show()
                self._resize_handles[pos] = h
        except Exception:
            logger.exception("Failed to create resize handles")
        self.split = QSplitter(Qt.Horizontal); root_v.addWidget(self.split); self.split.splitterMoved.connect(self.on_split)

        # Sidebar Left
        self.sb_l = QTabWidget(); self.sb_l.setStyleSheet("background:#111;")
        # Folders tab
        folders_tab = QWidget(); folders_lay = QVBoxLayout(folders_tab); folders_lay.setContentsMargins(0,0,0,0)
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True); self.tree.setIndentation(15)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection); self.tree.setMouseTracking(True)
        self.tree.setStyleSheet("background:#111; border:none;")
        self.tree.setItemDelegate(LibraryDelegate(self.tree, self.cfg, self.checked_paths)); folders_lay.addWidget(self.tree)
        self.ov = QWidget(self.tree.viewport()); self.ov.hide(); self.ov.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.backend.attach_prev(int(self.ov.winId()))

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
        folders_lay.addWidget(self.opt_shelf)
        footer = QHBoxLayout(); footer.setContentsMargins(5,5,5,5)
        btn_opts = QPushButton(icon=self.icns["settings"]); btn_opts.clicked.connect(lambda: self.opt_shelf.setVisible(not self.opt_shelf.isVisible()))
        btn_add = QPushButton("+", clicked=self.add_f); btn_add.setFixedSize(30,30)
        footer.addWidget(btn_opts); footer.addStretch(); footer.addWidget(btn_add); folders_lay.addLayout(footer)
        self.sb_l.addTab(folders_tab, "Folders")
        # Shows tab
        shows_tab = QWidget(); shows_lay = QVBoxLayout(shows_tab); shows_lay.setContentsMargins(0,0,0,0)
        self.shows_list = QListWidget(); self.shows_list.setStyleSheet("background:#111; border:none;")
        self.shows_list.itemDoubleClicked.connect(self.on_show_selected)
        shows_lay.addWidget(self.shows_list)
        self.sb_l.addTab(shows_tab, "Shows")
        self.split.addWidget(self.sb_l)

        # Center Player
        self.center_pane = QWidget(); self.center_lay = QVBoxLayout(self.center_pane); self.center_lay.setContentsMargins(0,0,0,0)
        self.v_out = VideoWidget(); self.v_out.setStyleSheet("background:black;"); self.v_out.double_clicked.connect(self.toggle_fs); self.v_out.mouse_moved.connect(self.wake_ui)
        self.center_lay.addWidget(self.v_out, 1)
        self.control_panel = QWidget(); cp_lay = QVBoxLayout(self.control_panel); cp_lay.setContentsMargins(0,0,0,0)
        self.sk = ClickSlider(Qt.Horizontal); self.sk.setRange(0, 1000); cp_lay.addWidget(self.sk)
        self.sk.sliderMoved.connect(lambda v: self.backend.main_player.set_time(int((v/1000)*self.backend.main_player.get_length())))
        ctrl_row = QHBoxLayout(); ctrl_row.setContentsMargins(10,5,10,10)
        bt_l = QPushButton(icon=self.icns["playlist"]); bt_l.clicked.connect(lambda: self.sb_l.setVisible(not self.sb_l.isVisible()))
        self.bp = QPushButton(icon=self.icns["play"]); self.bp.clicked.connect(self.backend.main_player.pause)
        # Add repeat and shuffle buttons
        self.bt_repeat = QPushButton("Repeat"); self.bt_repeat.clicked.connect(self.toggle_repeat)
        self.bt_shuffle = QPushButton("Shuffle"); self.bt_shuffle.clicked.connect(self.toggle_shuffle)
        self.vol = QSlider(Qt.Horizontal); self.vol.setFixedWidth(100); self.vol.setRange(0, 100); self.vol.setValue(self.cfg["volume"]); self.vol.valueChanged.connect(self.set_vol_save)
        self.lbl_t = QLabel("0:00 / 0:00"); bt_r = QPushButton(icon=self.icns["playlist"]); bt_r.clicked.connect(lambda: self.sb_r.setVisible(not self.sb_r.isVisible()))
        ctrl_row.addWidget(bt_l); ctrl_row.addSpacing(10); ctrl_row.addWidget(self.bp); ctrl_row.addWidget(self.bt_repeat); ctrl_row.addWidget(self.bt_shuffle); ctrl_row.addStretch()
        ctrl_row.addWidget(QLabel("Vol:")); ctrl_row.addWidget(self.vol); ctrl_row.addWidget(self.lbl_t); ctrl_row.addSpacing(10); ctrl_row.addWidget(bt_r)
        cp_lay.addLayout(ctrl_row); self.center_lay.addWidget(self.control_panel); self.backend.attach_main(int(self.v_out.winId())); self.split.addWidget(self.center_pane)

        # Right Sidebar (Playlist)
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
        # Track current playing path for title display
        self._now_playing = None
        # Player modes
        self.repeat_mode = 'none'  # none, one, all
        self.shuffle = False
        # Controller support
        if INPUTS_AVAILABLE:
            try:
                gamepads = inputs.devices.gamepads
                if gamepads:
                    self._controller_thread = threading.Thread(target=self._monitor_controller, daemon=True)
                    self._controller_thread.start()
                    logger.info("Controller monitoring started")
                else:
                    logger.info("No gamepads detected")
            except Exception:
                logger.exception("Failed to start controller monitoring")
        else:
            logger.info("Inputs library not available for controller support")

    def changeEvent(self, event):
        try:
            if event.type() == QEvent.WindowStateChange:
                # hide title bar in fullscreen
                is_fs = self.isFullScreen()
                try:
                    self._title_bar.setVisible(not is_fs)
                except Exception:
                    pass
                # update maximize/restore icon state
                try:
                    self._title_bar._update_max_icon()
                except Exception:
                    pass
        except Exception:
            logger.exception("Error handling changeEvent")
        return super().changeEvent(event)

    def resizeEvent(self, e):
        try:
            # position resize handles around the window edges
            r = self.rect()
            thickness = 8
            # edges
            if hasattr(self, '_resize_handles'):
                try:
                    self._resize_handles['left'].setGeometry(0, thickness, thickness, r.height()-2*thickness)
                    self._resize_handles['right'].setGeometry(r.width()-thickness, thickness, thickness, r.height()-2*thickness)
                    self._resize_handles['top'].setGeometry(thickness, 0, r.width()-2*thickness, thickness)
                    self._resize_handles['bottom'].setGeometry(thickness, r.height()-thickness, r.width()-2*thickness, thickness)
                    # corners (square)
                    self._resize_handles['topleft'].setGeometry(0, 0, thickness, thickness)
                    self._resize_handles['topright'].setGeometry(r.width()-thickness, 0, thickness, thickness)
                    self._resize_handles['bottomleft'].setGeometry(0, r.height()-thickness, thickness, thickness)
                    self._resize_handles['bottomright'].setGeometry(r.width()-thickness, r.height()-thickness, thickness, thickness)
                except Exception:
                    pass
        except Exception:
            logger.exception("Error positioning resize handles")
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
        self.populate_shows()
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
        # Removed hover video preview - always hide overlay
        self.ov.hide()
        self.backend.stop_prev()
        self._hover_preview = None
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

    def populate_shows(self):
        self.shows_list.clear()
        shows = self.db.get_all_shows()
        for show in shows:
            item = QListWidgetItem(show[2])  # name
            if show[4]:  # cached_image_path
                pixmap = QPixmap(show[4])
                if not pixmap.isNull():
                    item.setIcon(QIcon(pixmap.scaled(64, 96, Qt.KeepAspectRatio)))
            item.setData(Qt.UserRole, show[1])  # tvmaze_id
            self.shows_list.addItem(item)

    def on_show_selected(self, item):
        tvmaze_id = item.data(Qt.UserRole)
        # For now, just log; later expand to show seasons/episodes
        logger.info(f"Selected show: {item.text()} (ID: {tvmaze_id})")

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
                    pix = QPixmap(tp)
                    if not pix.isNull():
                        item.setData(0, Qt.DecorationRole, pix)
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