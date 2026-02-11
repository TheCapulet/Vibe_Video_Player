import os
import logging
from pathlib import Path
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt
import zipfile
import requests
import json

logger = logging.getLogger("ICON_UTILS")

def ensure_icon_variants(src_path="resources/icons/main.png", out_dir="resources/icons/sizes", sizes=(16,32,48,64,128,256)):
    """Ensure scaled icon variants exist and return a QIcon composed of them.

    - Loads `src_path` (expected to be a square PNG).
    - Writes scaled PNGs into `out_dir` named `main-<size>.png` if missing.
    - Returns a `QIcon` containing the generated pixmaps, or None on failure.
    """
    src = Path(src_path)
    out = Path(out_dir)
    # If the source isn't found relative to cwd, try the repository root (two parents up from this file)
    repo_root = Path(__file__).resolve().parents[2]
    if not src.exists():
        alt = repo_root / src_path
        if alt.exists():
            logger.debug("Icon source not found at %s, using repo root path %s", src, alt)
            src = alt
        else:
            # fallback: try installed icon pack path under resources/icons/<installed> (config)
            try:
                from app.util.config import load
                cfg = load()
                installed = cfg.get('installed_icon_pack', 'default')
                alt2 = repo_root / 'resources' / 'icons' / installed / Path(src_path).name
                if alt2.exists():
                    logger.debug("Using installed icon pack path %s", alt2)
                    src = alt2
                else:
                    logger.debug("Icon source not found at %s or %s", src, alt2)
            except Exception:
                logger.exception("Error while attempting icon fallback paths")
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


def list_available_icon_packs():
    # Return a small curated list of icon packs (name, url, license_url)
    return [
        {
            'name': 'Heroicons',
            'url': 'https://github.com/tailwindlabs/heroicons/archive/refs/heads/main.zip',
            'license_url': 'https://github.com/tailwindlabs/heroicons/blob/main/LICENSE'
        },
        {
            'name': 'Tabler',
            'url': 'https://github.com/tabler/tabler-icons/archive/refs/heads/master.zip',
            'license_url': 'https://github.com/tabler/tabler-icons/blob/master/LICENSE'
        },
        {
            'name': 'Iconoir',
            'url': 'https://github.com/iconoir-icons/iconoir/archive/refs/heads/main.zip',
            'license_url': 'https://github.com/iconoir-icons/iconoir/blob/master/LICENSE'
        }
    ]


def install_icon_pack(name, url, license_url=None):
    logger.info("Installing icon pack %s from %s", name, url)
    repo_root = Path(__file__).resolve().parents[2]
    dest = repo_root / 'resources' / 'icons' / name
    dest.mkdir(parents=True, exist_ok=True)
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        # save to temp zip
        tmp = repo_root / f"{name}.zip"
        with open(tmp, 'wb') as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        # extract
        with zipfile.ZipFile(tmp, 'r') as z:
            # extract only svg/png files into dest
            for info in z.infolist():
                if info.filename.lower().endswith(('.svg', '.png')):
                    out_name = Path(info.filename).name
                    with z.open(info) as srcf, open(dest / out_name, 'wb') as outf:
                        outf.write(srcf.read())
        tmp.unlink(missing_ok=True)
        # fetch license text
        if license_url:
            try:
                lr = requests.get(license_url, timeout=10)
                if lr.ok:
                    (dest / 'LICENSE.txt').write_text(lr.text, encoding='utf-8')
            except Exception:
                logger.exception("Failed to fetch license for %s", name)
        # record installed pack in config
        try:
            from app.util.config import load, save
            cfg = load(); cfg['installed_icon_pack'] = name; save(cfg)
        except Exception:
            logger.exception("Failed to update config with installed icon pack")
        logger.info("Installed icon pack %s", name)
        return True
    except Exception:
        logger.exception("Failed to install icon pack %s", name)
        return False
