import os

MAIN_PY_CONTENT = """
import sys
import os
from pathlib import Path

# Fix: Add the project root to the python path
# This allows 'import app.core' to work regardless of how the script is called.
root_path = str(Path(__file__).parent.parent.absolute())
if root_path not in sys.path:
    sys.path.insert(0, root_path)

from PySide6.QtWidgets import QApplication
from app.core.player import Player
from app.core.vlc_backend import VLCBackend
from app.ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)

    backend = VLCBackend()
    player = Player(backend)
    window = MainWindow(player, backend)

    window.show()
    
    # Ensure clean exit
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
"""

def fix():
    file_path = "app/main.py"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(MAIN_PY_CONTENT.strip())
    print(f"Fixed: {file_path}")

if __name__ == "__main__":
    fix()