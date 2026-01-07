import os
import logging
from pathlib import Path
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt

logger = logging.getLogger("ICON_UTILS")

def ensure_icon_variants(src_path="resources/icons/main.png", out_dir="resources/icons/sizes", sizes=(16,32,48,64,128,256)):
    """Ensure scaled icon variants exist and return a QIcon composed of them.

    - Loads `src_path` (expected to be a square PNG).
    - Writes scaled PNGs into `out_dir` named `main-<size>.png` if missing.
    - Returns a `QIcon` containing the generated pixmaps, or None on failure.
    """
    src = Path(src_path)
    out = Path(out_dir)
    try:
        out.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("Failed to create icon output directory %s", out)
        return None

    if not src.exists():
        logger.warning("Icon source not found: %s", src)
        return None

    pix = QPixmap(str(src))
    if pix.isNull():
        logger.warning("Failed to load pixmap from %s", src)
        return None

    icon = QIcon()
    for s in sizes:
        tgt = out / f"main-{s}.png"
        try:
            if not tgt.exists():
                scaled = pix.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                scaled.save(str(tgt), "PNG")
            pm = QPixmap(str(tgt))
            if not pm.isNull():
                icon.addPixmap(pm)
        except Exception:
            logger.exception("Failed to create or add icon size %s", s)
    return icon
