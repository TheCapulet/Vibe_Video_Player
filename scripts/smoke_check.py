"""Simple smoke-check script: instantiate VLCBackend without starting UI.

Run from repository root:

python scripts/smoke_check.py
"""
from app.core.vlc_backend import VLCBackend
from app.util.logger import setup_app_logger

logger = setup_app_logger("SMOKE")

if __name__ == "__main__":
    try:
        b = VLCBackend()
        logger.info("VLCBackend ready: %s", b.ready)
    except Exception:
        logger.exception("Smoke check failed")
