from PySide6.QtWidgets import *
from PySide6.QtCore import *
import app.util.config as config

class SettingsPanel(QWidget):
    changed = Signal()

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg # Shared reference from MainWindow
        self.setStyleSheet("background:#181818; border-top:1px solid #333;")
        l = QGridLayout(self)

        self.tog_static = QCheckBox("Thumbnails"); self.tog_static.setChecked(self.cfg["show_static"])
        self.tog_video = QCheckBox("Hover Video"); self.tog_video.setChecked(self.cfg["show_video"])
        self.tog_hide = QCheckBox("Autohide (Window)"); self.tog_hide.setChecked(self.cfg["autohide_windowed"])
        
        for i, t in enumerate([self.tog_static, self.tog_video, self.tog_hide]):
            t.toggled.connect(self.update_cfg)
            l.addWidget(t, i, 0)

        def mk_sl(lbl, key, min_v, max_v, col):
            w = QWidget(); vl = QVBoxLayout(w); vl.setContentsMargins(5,0,5,0)
            val = self.cfg[key]
            txt = QLabel(f"{lbl}: {val}"); txt.setStyleSheet("font-size:10px; color:#888;")
            s = QSlider(Qt.Horizontal); s.setRange(min_v, max_v); s.setValue(val)
            s.valueChanged.connect(lambda v, k=key, t=txt, lab=lbl: self.set_val(k, v, t, lab))
            vl.addWidget(txt); vl.addWidget(s); l.addWidget(w, 0, col, 3, 1)

        mk_sl("Text", "text_size", 8, 30, 1)
        mk_sl("Size", "card_width", 100, 500, 2)
        mk_sl("Time", "preview_start", 0, 900, 3)

    def set_val(self, k, v, t, lab):
        self.cfg[k] = v; t.setText(f"{lab}: {v}")
        config.save(self.cfg); self.changed.emit()

    def update_cfg(self):
        self.cfg["show_static"] = self.tog_static.isChecked()
        self.cfg["show_video"] = self.tog_video.isChecked()
        self.cfg["autohide_windowed"] = self.tog_hide.isChecked()
        config.save(self.cfg); self.changed.emit()