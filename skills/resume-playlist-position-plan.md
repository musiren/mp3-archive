# Plan: Remember the Playlist Cursor & Lazy Playlist Restore

Target: the Android app (`src/main_window_android.py`), the playback service
(`src/audio_service.py`) and the shared, GUI-independent modules
(`src/service_ipc.py`, `src/mp3_manager.py`).

## Problem 1 — playback restarts at the first track after a restart

The session cursor (`now_path` / `now_index` / `now_pos` in the `app_state`
table) is only written by `Mp3ArchiveApp._save_app_state()`, which runs in
`on_pause` / `on_stop`. Two gaps follow, and a nightly phone reboot hits both:

1. **The cursor is never updated while the service plays.** The foreground
   service (`audio_service.py`) owns auto-advance and keeps changing tracks
   after the UI is backgrounded or killed, but it opens the state DB read-only
   (`service_ipc.read_resume_state`) and has no way to write the cursor. The
   saved cursor is therefore a snapshot from the moment the app was
   backgrounded — and nothing at all is saved when the UI process is killed
   without `on_pause`.
2. **The cursor is discarded when playback ends.** `AudioService.stop()` sets
   `_index = -1` / `_path = ""` and pushes an idle state; the UI's
   `_apply_service_state` then clears `_playing_path`. Reaching the end of the
   queue in `sequential` mode therefore leaves `_playing_path` empty and
   `_resume_index` at -1, so the next `_save_app_state()` stores
   `now_path = ""`, `now_index = -1`. On the next launch
   `_restore_now_playing()` returns early and the play button falls back to
   `_start_index()` — index 0, the first track.

### Fix

- `service_ipc.write_resume_state(db_path, path, index, position, seed)`: the
  write counterpart of `read_resume_state`, upserting the cursor rows into an
  existing state DB (it never creates or migrates anything).
- `AudioService` persists the cursor itself, so progress survives even with no
  UI process alive:
  - on every track start (`_play_index`),
  - periodically while playing (~10 s, from `tick`), so an abrupt kill keeps
    the position,
  - in `stop()` — the last played track is kept as the cursor (position 0)
    instead of being wiped, skipped only when the queue itself is gone.
  - `_start_queue()` falls back to that remembered cursor when `_index` was
    cleared by a stop.
- `Mp3ArchiveApp` writes the cursor as soon as the current track changes
  (`_play_queue_index`, and `_apply_service_state` when the service
  auto-advances), plus a throttled position write in the SoundLoader fallback.
- `stop_playback()` retains the cursor (`_retain_cursor()`) instead of losing
  it, so an explicit stop or an end-of-queue still resumes that track.
- `_save_app_state()` falls back to the queue's current index, and leaves the
  stored cursor untouched when it has nothing better to write (it must never
  overwrite a good cursor with an empty one).
- `toggle_play_pause()` starts from the queue's current index when no pending
  resume target is set, and only uses `_start_index()` for a genuinely fresh
  queue.

The playlist order itself is untouched: the queue rows (or the `.list` source)
and the shuffle seed are already persisted, so restoring the index is enough
for `playlist.advance()` to continue inside the same seeded shuffle order
rather than restarting it.

## Problem 2 — slow launch with a large playlist

`_restore_session()` rebuilds the queue synchronously before the first frame:
for every saved path it runs an `os.path.isfile()` stat **and** a separate
`Mp3Manager.get_by_path()` query. A few hundred tracks therefore cost a few
hundred stats plus a few hundred SQLite round-trips on the launch path.

### Fix (lazy hydration)

- `Mp3Manager.get_many_by_path(paths)`: one chunked `WHERE path IN (…)` query
  returning `{path: row}`, replacing the per-track lookups.
- `_restore_session()` paints the queue immediately from the saved paths with
  placeholder display data (`_placeholder_items`) — no stats, no DB work — and
  restores the cursor, so the player is usable on the first frame.
- `_hydrate_queue()` then fills in artist/title and checks file existence in
  chunks from the Kivy clock (`_hydrate_items`), one frame per chunk. Missing
  files are removed at the end of the pass, the cursor is re-resolved by path
  across the removals, and the service is re-synced only if something was
  dropped.
- Hydration must not call `_queue_changed()`: the playlist order, the shuffle
  seed and the `.list` source all stay as restored.

## Test updates (same commits as the code)

- `test_service_ipc.py`: `write_resume_state` round-trip through
  `read_resume_state`, missing DB handled, `seed=0` keeps the stored seed.
- `test_mp3_manager.py`: `get_many_by_path` keying, unknown paths, chunking
  above the SQLite variable limit.
- `test_main_window_android.py`: `_save_cursor`, `_retain_cursor`,
  `_save_app_state` fallbacks (queue current index; no wipe when empty),
  `_placeholder_items`, `_hydrate_items` (metadata fill + missing detection).

## Out of scope

- The desktop PyQt app (`main_window.py`), which does not persist its
  playlist at all.
- On-device APK verification cannot run in this environment (no adb/gh CLI);
  the routine in CLAUDE.md must be run after the branch is pushed.
