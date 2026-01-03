import os, hashlib, re
from pathlib import Path
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

def get_h(p): return hashlib.md5(p.lower().replace("\\","/").encode()).hexdigest()

class LibraryDelegate(QStyledItemDelegate):
    def __init__(self, parent, cfg, checked_set):
        super().__init__(parent); self.cfg = cfg; self.checked_set = checked_set

    def paint(self, painter, option, index):
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(45, 45, 45))
        
        path = index.data(Qt.UserRole)
        if path and not os.path.isdir(path):
            tw, th = self.cfg["card_width"], int(self.cfg["card_width"] * 0.56)
            
            # 1. Checkbox (Hit zone: left 35px)
            cb_rect = QRect(option.rect.left() + 5, option.rect.top() + (th // 2) - 4, 18, 18)
            opt = QStyleOptionButton(); opt.rect = cb_rect; opt.state = QStyle.State_Enabled
            opt.state |= QStyle.State_On if path in self.checked_set else QStyle.State_Off
            QApplication.style().drawControl(QStyle.CE_CheckBox, opt, painter)
            
            # 2. Thumbnail
            r_img = QRect(option.rect.left() + 35, option.rect.top() + 5, tw, th)
            painter.fillRect(r_img, Qt.black)
            pix = index.data(Qt.DecorationRole)
            if isinstance(pix, QPixmap): 
                painter.drawPixmap(r_img, pix.scaled(r_img.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
            # 3. Text
            r_txt = QRect(option.rect.left() + 35, option.rect.top() + th + 8, tw, self.cfg["text_size"] * 2.5)
            painter.setPen(QColor(200, 200, 200))
            f = painter.font(); f.setPointSize(self.cfg["text_size"]); painter.setFont(f)
            painter.drawText(r_txt, Qt.AlignLeft | Qt.TextWordWrap, index.data(Qt.DisplayRole))
        else:
            super().paint(painter, option, index)
        painter.restore()

    def sizeHint(self, option, index):
        path = index.data(Qt.UserRole)
        if path and not os.path.isdir(path):
            tw = self.cfg["card_width"]
            return QSize(tw + 45, int(tw * 0.56) + (self.cfg["text_size"] * 2.5) + 15)
        return QSize(200, 32)

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonPress:
            if event.pos().x() < option.rect.left() + 35:
                p = index.data(Qt.UserRole)
                if p in self.checked_set: self.checked_set.remove(p)
                else: self.checked_set.add(p)
                model.dataChanged.emit(index, index)
                return True
        return super().editorEvent(event, model, option, index)