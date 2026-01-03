import sys, os
from pathlib import Path
root_path = str(Path(__file__).parent.parent.absolute())
if root_path not in sys.path: sys.path.insert(0, root_path)
from PySide6.QtWidgets import QApplication
from app.core.player import Player
from app.core.vlc_backend import VLCBackend
from app.ui.main_window import MainWindow
from app.util.logger import setup_app_logger, crash_handler
def main():
    log = setup_app_logger("MAIN")
    sys.excepthook = crash_handler
    app = QApplication(sys.argv)
    backend = VLCBackend()
    player = Player(backend)
    window = MainWindow(player, backend)
    window.show()
    sys.exit(app.exec())
if __name__ == "__main__":
    main()