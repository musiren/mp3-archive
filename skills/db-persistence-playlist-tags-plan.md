# Plan: Library DB Persistence + Playlist Tag View (Android)

## Request

1. Save the library database when the app exits and reopen it on the next
   launch. When the user has never scanned, there is nothing to restore —
   ignore. In the scan picker, selecting a **.db file** loads that database
   and shows its list; selecting a **directory** scans it as before.
2. Long-pressing a song in the play queue (재생목록) must also offer the tag
   detail view (자세히), like the library rows already do.

## Design

### 1. Per-directory library DB + restore on launch

Today the app keeps a single internal DB in app-private storage
(`app_storage_path()/mp3_archive.db`), which is invisible to the in-app
file manager, so there is no DB file the user could ever pick.

New architecture (mirrors the desktop app's per-directory
`.mp3-archive.db`):

- `self._state` — `Mp3Manager` on the internal DB. Always open; owns
  `app_state` + `play_queue` (session persistence) and doubles as the
  *default* library for backward compatibility.
- `self._manager` — the **library** DB. Defaults to `self._state`; swapped
  by `_set_library_db(path)` which also records the choice under the
  `library_db` app-state key (empty = internal).
- **Scanning a directory** now writes into `<directory>/mp3_archive.db`
  (visible, lives with the music, re-selectable later). Re-picking the same
  folder resumes its DB incrementally. If the directory is not writable the
  scan falls back to the internal DB with the legacy replace-the-library
  semantics.
- **Launch**: `_restore_library_db()` reads the `library_db` key and
  reopens the file when it still exists; `_last_dir` becomes its directory
  so the refresh button keeps working. Never scanned → key empty → internal
  DB → previous behaviour.
- **Exit**: SQLite commits continuously; `_save_app_state` re-records the
  `library_db` pointer and `on_stop` closes both connections.
- **Picker** (`MDFileManager`): `selector="any"` + `ext=[".db"]`, so the
  listing shows folders plus `.db` files only. A `.db` selection calls
  `_load_database(path)` (open + refresh list + status); a folder selection
  scans as before.

State accessors (`get_state`/`set_state`/`save_queue`/`load_queue`) move
from `self._manager` to `self._state` so session state never follows an
external library DB.

### 2. Queue long-press → 자세히

- Split `_open_detail(row)` into a thin wrapper plus `_show_tag_detail(path)`
  holding the dialog body (it only ever used `row.path`).
- Add a "자세히" action to `open_queue_actions` that resolves the queue
  item's path and calls `_show_tag_detail`. Tracks missing from the library
  DB still show file-level info (all tag/stream readers tolerate that).

## Files

- `src/main_window_android.py` — all changes above.
- `test/test_main_window_android.py` — point session-persistence stubs at
  `_state`; new tests for `_set_library_db` / `_restore_library_db` /
  `_on_dir_selected` routing and the queue 자세히 action.

## Verification

- `python -m unittest discover -s test -v` before commit.
- On-device routine (build → install → manual check) after push, per
  CLAUDE.md — requires the ADB-connected phone.
