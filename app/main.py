import sys, os, importlib, subprocess
import shutil
from pathlib import Path

root_path = str(Path(__file__).parent.parent.absolute())
if root_path not in sys.path: sys.path.insert(0, root_path)

# now that project root is on sys.path, import our logger
from app.util.logger import setup_app_logger

# Map pip package names to importable module names when they differ
_PKG_TO_MODULE = {
    'PySide6': 'PySide6',
    'python-vlc': 'vlc',
    'requests': 'requests',
    'inputs': 'inputs'
}

def _read_requirements(req_file: Path):
    if not req_file.exists():
        return []
    lines = []
    for l in req_file.read_text().splitlines():
        l = l.strip()
        if not l or l.startswith('#'):
            continue
        # strip version specifiers for import lookup
        pkg = l.split('==')[0].split('>=')[0].split('>')[0].strip()
        lines.append(pkg)
    return lines


# initialize module logger early
_LOGGER = setup_app_logger('MAIN_DEP')
_LOGGER.debug("root_path=%s", root_path)

def _missing_packages(req_file: Path):
    pkgs = _read_requirements(req_file)
    missing = []
    for p in pkgs:
        mod = _PKG_TO_MODULE.get(p, p)
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(p)
            _LOGGER.debug("Missing package for import lookup: %s -> module %s", p, mod)
    return missing

def _install_requirements(req_file: Path):
    cmd = [sys.executable, '-m', 'pip', 'install', '-r', str(req_file)]
    _LOGGER.info("Running pip install: %s", cmd)
    rc = subprocess.call(cmd)
    _LOGGER.info("pip returned code %s", rc)
    if rc == 0:
        _LOGGER.debug("pip install succeeded")
        return rc

    # If install failed, attempt elevated install depending on platform
    try:
        _LOGGER.debug("Attempting elevated install fallback on platform: %s", sys.platform)
        if sys.platform.startswith('win'):
            # Use ShellExecute runas to prompt UAC and run pip install
            try:
                import ctypes
                from ctypes import wintypes
                ShellExecuteW = ctypes.windll.shell32.ShellExecuteW
                params = f"-m pip install -r \"{str(req_file)}\""
                # ShellExecuteW returns >32 on success
                ret = ShellExecuteW(None, 'runas', sys.executable, params, None, 1)
                _LOGGER.debug("ShellExecuteW returned %s", ret)
                return 0 if int(ret) > 32 else rc
            except Exception:
                _LOGGER.exception("ShellExecute runas failed")
                return rc
        else:
            # Try pkexec, then sudo as fallbacks
            try:
                pkexec = shutil.which('pkexec')
                if pkexec:
                    cmd2 = ['pkexec', sys.executable, '-m', 'pip', 'install', '-r', str(req_file)]
                    _LOGGER.info("Running pkexec elevated install: %s", cmd2)
                    rc2 = subprocess.call(cmd2)
                    _LOGGER.info("pkexec returned %s", rc2)
                    return rc2
            except Exception:
                _LOGGER.exception("pkexec elevated install failed")
                pass
            try:
                # sudo will prompt in terminal; this may fail in GUI-only environments
                cmd3 = ['sudo', sys.executable, '-m', 'pip', 'install', '-r', str(req_file)]
                _LOGGER.info("Running sudo elevated install: %s", cmd3)
                rc3 = subprocess.call(cmd3)
                _LOGGER.info("sudo returned %s", rc3)
                return rc3
            except Exception:
                _LOGGER.exception("sudo elevated install failed")
                return rc
    except Exception:
        _LOGGER.exception("Unexpected error during elevated install fallback")
        return rc

def ensure_dependencies_and_maybe_install():
    req_file = Path(root_path) / 'requirements.txt'
    missing = _missing_packages(req_file)
    if not missing:
        _LOGGER.debug("No missing packages")
        return True, False

    # If PySide6 is missing we cannot show a Qt dialog; fall back to console prompt
    use_console = 'PySide6' in missing
    text = f"Missing dependencies: {', '.join(missing)}\nInstall now?"
    try:
        if use_console:
            _LOGGER.info("Missing packages detected (console mode): %s", missing)
            resp = input(text + " [Y/n]: ")
            _LOGGER.debug("User response: %s", resp)
            if resp.strip().lower() in ('', 'y', 'yes'):
                rc = _install_requirements(req_file)
                _LOGGER.info("Install completed with code %s", rc)
                return (rc == 0), (rc == 0)
            return False, False
        else:
            # show a simple Qt prompt since PySide6 is available
            _LOGGER.info("Missing packages detected (GUI mode): %s", missing)
            from PySide6.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance() or QApplication([])
            reply = QMessageBox.question(None, "Install Dependencies", text, QMessageBox.Yes | QMessageBox.No)
            _LOGGER.debug("GUI prompt reply: %s", reply)
            if reply == QMessageBox.Yes:
                rc = _install_requirements(req_file)
                _LOGGER.info("Install completed with code %s", rc)
                return (rc == 0), (rc == 0)
            return False, False
    except Exception:
        _LOGGER.exception("Exception while prompting/installing dependencies; falling back to console prompt")
        # fallback to console
        try:
            resp = input(text + " [Y/n]: ")
            if resp.strip().lower() in ('', 'y', 'yes'):
                rc = _install_requirements(req_file)
                _LOGGER.info("Install completed with code %s", rc)
                return (rc == 0), (rc == 0)
        except Exception:
            _LOGGER.exception("Console fallback prompt failed")
        return False, False
def main():
    # Ensure dependencies first; if installation was performed, restart the process
    try:
        ok, installed_now = ensure_dependencies_and_maybe_install()
    except Exception:
        ok, installed_now = False, False
    if not ok:
        print("Required dependencies are not installed. Exiting.")
        sys.exit(1)
    # If we just installed dependencies, restart the process so new packages are available
    if installed_now:
        print("Dependencies installed — restarting application...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    from app.util.logger import setup_app_logger, crash_handler, hook_std_streams
    from app.core.player import Player
    from app.core.vlc_backend import VLCBackend
    try:
        from app.ui.main_window import MainWindow
    except Exception:
        # If the full MainWindow is missing or broken, fall back to MinimalMainWindow
        from app.ui.main_window import MinimalMainWindow as MainWindow
        _LOGGER.exception("Failed to import full MainWindow; using MinimalMainWindow fallback")
    from PySide6.QtWidgets import QApplication
    from app.util.icon_utils import ensure_icon_variants

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