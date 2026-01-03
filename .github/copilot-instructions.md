# Copilot / AI Agent Instructions — Vibe_Video_Player

Quick actionable guidance to help an AI coding agent become productive in this repo.

## Big picture
- **What it is:** A desktop video player using PySide6 for UI and python-vlc for playback.
- **Runtime components:** UI process (PySide6) + a small thumbnail worker started as a subprocess (`app/util/worker.py`). See [app/main.py](app/main.py#L1-L40).
- **Separation of concerns:** `app/core` contains playback backend (`vlc_backend.py`) and a thin `Player` wrapper; `app/ui` contains UI widgets and delegates; `app/util` contains config, logging and worker utilities.

## Key files & patterns (use these as primary anchors)
- **Entry / run:** [app/main.py](app/main.py#L1-L40) — sets up `VLCBackend`, `Player`, `MainWindow`, and global crash handler.
- **Playback backend:** [app/core/vlc_backend.py](app/core/vlc_backend.py#L1-L200) — two libvlc instances are used (main player + preview player). Important public methods: `open_main`, `open_prev`, `attach_main`, `attach_prev`, `set_vol`, `get_state_safe`, `release`.
- **Player wrapper:** [app/core/player.py](app/core/player.py#L1-L200) — very small; forwards calls to the backend. Prefer updating backend when adding playback features.
- **UI & thumbnails:** [app/ui/main_window.py](app/ui/main_window.py#L1-L400) — UI logic, playlist handling, and worker orchestration. Thumbnail hashing uses `get_h()` in [app/ui/library.py](app/ui/library.py#L1-L40).
- **Thumbnail worker:** [app/util/worker.py](app/util/worker.py#L1-L200) — launched with `subprocess.Popen([sys.executable, ... worker.py])` and fed lines of `'{path}|{seek}'` on stdin; writes snapshots into `resources/thumbs/<md5>.jpg`.
- **Config storage:** `app/util/config.py` reads/writes `config.json` in the working directory (not packaged resource). Be aware of path handling using `Path.as_posix()`.
- **Dependencies:** [requirements.txt](requirements.txt#L1-L20) — `PySide6`, `python-vlc` (libvlc native dependency required at runtime).

## How to run / build (developer workflows)
- Create a venv and install deps:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
- Run the app from the repository root (important because `config.json` is read/written from cwd):
```bash
python app/main.py
```
- Build: a PyInstaller spec exists at `build/pyinstaller.spec`. Typical usage (Windows):
```bash
pyinstaller build/pyinstaller.spec
```
Note: when packaging, ensure libvlc (and its matching python-vlc) are available to the bundled app and include `app/util/worker.py` and `resources/thumbs`.

## Project-specific conventions & gotchas
- The UI expects `resources/thumbs/<md5>.jpg` thumbnails. Hashing is lowercased posix path MD5 using `get_h()` in [app/ui/library.py](app/ui/library.py#L1-L40).
- Worker IPC is simple text on stdin; tasks are idempotent — worker checks for an existing thumbnail and skips if present.
- `app/util/config.py` uses a plain `config.json` filename (no folder). Run commands from project root or tests will read/write the wrong file.
- The code often swallows exceptions (many `try: ... except: pass`). When changing behavior, prefer adding explicit logging via `app/util/logger.py` which writes `app_debug.log`.
- UI thread directly calls some libvlc player methods (e.g., `main_player.set_time`, `main_player.get_length`) — be careful when refactoring threading or moving operations off the GUI thread.

## Integration points to be careful about
- `VLCBackend` interacts with native libvlc; changes to instance flags (e.g. hardware accel) affect behavior. See `config.json` keys like `hw_accel` in root config.
- `MainWindow` starts the worker via `sys.executable` — packaging or virtualenv changes must preserve that bundling approach.
- Thumbnails and previews use a second vlc instance; concurrency uses a simple `threading.Lock()` inside `VLCBackend`.

## Examples of typical agent tasks & where to change code
- Add a new playback feature (e.g., subtitle toggle): modify `app/core/vlc_backend.py` to expose libvlc subtitle APIs and update `Player` and UI calls in `app/ui/main_window.py`.
- Improve thumbnail generation: edit [app/util/worker.py](app/util/worker.py#L1-L200) and ensure `MainWindow` still writes the same stdin format.
- Add settings UI: update `app/config.json` defaults and `app/util/config.py`, then render controls in `app/ui/main_window.py` (see `mk_sl()` pattern for sliders and `save_toggles()` saving flow).

## Debugging tips
- Check `app_debug.log` (created by `app/util/logger.py`) for runtime logs.
- Worker errors are written to stderr by the worker process — run `python app/util/worker.py` manually to reproduce thumbnail issues.
- If playback fails, confirm native libvlc is installed and that `python-vlc` can load it; `VLCBackend.__init__` sets `ready = False` on failure.

If anything here is unclear or you'd like me to expand specific sections (packaging tips, tests, or a short contributor checklist), tell me what to add and I'll iterate.
