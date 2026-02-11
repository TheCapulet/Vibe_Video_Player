from PySide6.QtWidgets import *
from PySide6.QtCore import *
import app.util.config as config
from app.util.icon_utils import list_available_icon_packs, install_icon_pack
from app.util.logger import setup_app_logger
import threading

logger = setup_app_logger('SETTINGS_PANEL')


class SettingsPanel(QWidget):
    changed = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg # Shared reference from MainWindow
        self.setStyleSheet("background:#181818; border-top:1px solid #333;")
        l = QGridLayout(self)

        self.tog_static = QCheckBox("Thumbnails"); self.tog_static.setChecked(self.cfg.get("show_static", True))
        self.tog_video = QCheckBox("Hover Video"); self.tog_video.setChecked(self.cfg.get("show_video", True))
        self.tog_hide = QCheckBox("Autohide (Window)"); self.tog_hide.setChecked(self.cfg.get("autohide_windowed", False))
        
        for i, t in enumerate([self.tog_static, self.tog_video, self.tog_hide]):
            t.toggled.connect(self.update_cfg)
            l.addWidget(t, i, 0)

        def mk_sl(lbl, key, min_v, max_v, col):
            w = QWidget(); vl = QVBoxLayout(w); vl.setContentsMargins(5,0,5,0)
            val = self.cfg.get(key, 0)
            txt = QLabel(f"{lbl}: {val}"); txt.setStyleSheet("font-size:10px; color:#888;")
            s = QSlider(Qt.Horizontal); s.setRange(min_v, max_v); s.setValue(val)
            s.valueChanged.connect(lambda v, k=key, t=txt, lab=lbl: self.set_val(k, v, t, lab))
            vl.addWidget(txt); vl.addWidget(s); l.addWidget(w, 0, col, 3, 1)

        mk_sl("Text", "text_size", 8, 30, 1)
        mk_sl("Size", "card_width", 100, 500, 2)
        mk_sl("Time", "preview_start", 0, 900, 3)

        # Icon pack controls
        self.lbl_installed = QLabel(f"Installed icon pack: {self.cfg.get('installed_icon_pack', 'default')}")
        l.addWidget(self.lbl_installed, 4, 0, 1, 2)
        self.auto_accept = QCheckBox("Automatically accept icon pack licenses")
        self.auto_accept.setChecked(self.cfg.get('auto_accept_licenses', False))
        self.auto_accept.toggled.connect(self.on_toggle_auto_accept)
        l.addWidget(self.auto_accept, 5, 0, 1, 2)
        self.store_btn = QPushButton("Get More Icon Packs")
        self.store_btn.clicked.connect(self.open_store)
        l.addWidget(self.store_btn, 6, 0)

    def set_val(self, k, v, t, lab):
        self.cfg[k] = v; t.setText(f"{lab}: {v}")
        config.save(self.cfg); self.changed.emit()

    def update_cfg(self):
        self.cfg["show_static"] = self.tog_static.isChecked()
        self.cfg["show_video"] = self.tog_video.isChecked()
        self.cfg["autohide_windowed"] = self.tog_hide.isChecked()
        config.save(self.cfg); self.changed.emit()

    def on_toggle_auto_accept(self, s):
        self.cfg['auto_accept_licenses'] = bool(s)
        config.save(self.cfg)
        logger.info('auto_accept_licenses set to %s', self.cfg['auto_accept_licenses'])

    def open_store(self):
        packs = list_available_icon_packs()
        dlg = QDialog(self)
        dlg.setWindowTitle('Icon Pack Store')
        lay = QVBoxLayout(dlg)
        for p in packs:
            row = QHBoxLayout()
            lbl = QLabel(p['name'])
            row.addWidget(lbl)
            btn = QPushButton('Install')
            def make_cb(pack):
                def cb():
                    self.install_pack(pack)
                return cb
            btn.clicked.connect(make_cb(p))
            row.addWidget(btn)
            lay.addLayout(row)
        dlg.exec_()

    def install_pack(self, pack):
        name = pack['name']
        url = pack['url']
        license_url = pack.get('license_url')
        if self.cfg.get('auto_accept_licenses') or self.cfg.get('accepted_icon_licenses', {}).get(name):
            threading.Thread(target=lambda: self._install_and_refresh(name, url, license_url), daemon=True).start()
            return
        text = f"Install {name}?"
        resp = QMessageBox.question(self, 'Install Icon Pack', text, QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            return
        # fetch license
        lic_text = ''
        try:
            import requests
            if license_url:
                r = requests.get(license_url, timeout=10)
                if r.ok:
                    lic_text = r.text
        except Exception:
            logger.exception('Failed to fetch license')
        lic_dlg = QDialog(self)
        lic_dlg.setWindowTitle(f"{name} License")
        llay = QVBoxLayout(lic_dlg)
        ta = QTextEdit(); ta.setReadOnly(True); ta.setPlainText(lic_text or 'License could not be fetched; see online.')
        llay.addWidget(ta)
        b_accept = QPushButton('Accept and Install'); b_decl = QPushButton('Decline')
        h = QHBoxLayout(); h.addWidget(b_accept); h.addWidget(b_decl); llay.addLayout(h)
        def do_accept():
            self.cfg.setdefault('accepted_icon_licenses', {})[name] = True
            config.save(self.cfg)
            lic_dlg.accept()
            threading.Thread(target=lambda: self._install_and_refresh(name, url, license_url), daemon=True).start()
        def do_decl():
            lic_dlg.reject()
        b_accept.clicked.connect(do_accept); b_decl.clicked.connect(do_decl)
        lic_dlg.exec_()

    def _install_and_refresh(self, name, url, license_url):
        ok = install_icon_pack(name, url, license_url)
        if ok:
            self.cfg = config.load()
            self.lbl_installed.setText(f"Installed icon pack: {self.cfg.get('installed_icon_pack', 'default')}")
            logger.info('Installed icon pack %s', name)
        else:
            logger.error('Failed to install icon pack %s', name)