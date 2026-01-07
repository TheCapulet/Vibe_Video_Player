import sys, os
from pathlib import Path
root_path = str(Path(__file__).parent.parent.absolute())
if root_path not in sys.path: sys.path.insert(0, root_path)
from PySide6.QtWidgets import QApplication
from app.core.player import Player
from app.core.vlc_backend import VLCBackend
from app.ui.main_window import MainWindow
from app.util.logger import setup_app_logger, crash_handler, hook_std_streams
from app.util.icon_utils import ensure_icon_variants
def main():
    log = setup_app_logger("MAIN")
    # Redirect stdout/stderr into logging to capture all output
    hook_std_streams(log)
    sys.excepthook = crash_handler
    # On Windows, set an explicit AppUserModelID so the taskbar uses our app icon
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.vibe.videoplayer")
        except Exception:
            log.exception("Failed to set AppUserModelID")
    app = QApplication(sys.argv)
    # Ensure icon variants are generated and set application icon
    try:
        icon = ensure_icon_variants()
        if icon:
            app.setWindowIcon(icon)
    except Exception:
        log.exception("Failed to set application icon")
    backend = VLCBackend()
    player = Player(backend)
    window = MainWindow(player, backend)
    window.show()
    sys.exit(app.exec())
if __name__ == "__main__":
    main()