v083.1 - 2026-01-06
- Files changed:
  - app/ui/main_window.py
- Summary:
  - Fix maximize/restore behavior: store/restore normal geometry and ensure restore reapplies geometry.
  - Add bottom-right QSizeGrip to allow resizing while using frameless window.
  - Update TitleBar to use platform icons and refresh max/restore icon on window state changes.
  - Populate folder expansions on a background thread to avoid UI blocking (fix library lockups during large folder scans).
  - Update main title label when a media item starts playing.
- Notes:
  - Tested in-repo by static inspection. Will run the app after user confirmation to verify runtime behavior.

