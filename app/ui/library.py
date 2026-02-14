import os, hashlib, re
from pathlib import Path
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

def get_h(p): return hashlib.md5(p.lower().replace("\\","/").encode()).hexdigest()

class LibraryDelegate(QStyledItemDelegate):
    def __init__(self, parent, cfg, checked_set, db):
        super().__init__(parent); self.cfg = cfg; self.checked_set = checked_set; self.db = db
    
    def paint(self, painter, option, index):
        painter.save()
        if option.state & QStyle.State_Selected: painter.fillRect(option.rect, QColor(45, 45, 45))
        p = index.data(Qt.UserRole)
        is_video = any(str(p).lower().endswith(ex) for ex in ['.mp4','.mkv','.avi'])
        
        if is_video:
            tw, th = self.cfg["card_width"], int(self.cfg["card_width"] * 0.56)
            # Checkbox hit-zone padding
            cb_rect = QRect(option.rect.left() + 8, option.rect.top() + (th // 2) - 4, 18, 18)
            opt = QStyleOptionButton(); opt.rect = cb_rect; opt.state = QStyle.State_Enabled
            opt.state |= QStyle.State_On if p in self.checked_set else QStyle.State_Off
            QApplication.style().drawControl(QStyle.CE_CheckBox, opt, painter)
            # Thumbnail
            r_img = QRect(option.rect.left() + 35, option.rect.top() + 5, tw, th)
            painter.fillRect(r_img, Qt.black)
            pix = index.data(Qt.DecorationRole)
            if isinstance(pix, QPixmap): painter.drawPixmap(r_img, pix.scaled(r_img.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            # Text
            r_txt = QRect(option.rect.left() + 35, option.rect.top() + th + 8, tw, self.cfg["text_size"] * 2.5)
            painter.setPen(QColor(200, 200, 200))
            f = painter.font(); f.setPointSize(self.cfg["text_size"]); painter.setFont(f)
            text = index.data(Qt.DisplayRole)
            if self.cfg.get("show_metadata", False):
                # Try to get metadata
                video_record = self.db.get_video(p)
                if video_record and video_record[9]:  # episode_id
                    episode = self.db.get_episode_by_id(video_record[9])
                    if episode:
                        season = self.db.get_season_by_id(episode[1])
                        if season:
                            show = self.db.get_show(season[1])
                            if show:
                                text = f"{show[2]} - S{season[2]:02d}E{episode[2]:02d}\n{episode[3]}"
            painter.drawText(r_txt, Qt.AlignLeft | Qt.TextWordWrap, text)
        else:
            super().paint(painter, option, index) # Native Folder Drawing
        painter.restore()

    def sizeHint(self, option, index):
        p = index.data(Qt.UserRole)
        is_video = any(str(p).lower().endswith(ex) for ex in ['.mp4','.mkv','.avi'])
        if is_video:
            tw = self.cfg["card_width"]
            return QSize(tw + 45, int(tw * 0.56) + (self.cfg["text_size"] * 2.5) + 15)
        return QSize(200, 32)