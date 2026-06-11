# Plan: App-State Persistence & Deterministic Shuffle

Target: the Android app (`src/main_window_android.py`) plus the shared,
GUI-independent modules (`playlist.py`, `service_ipc.py`, `audio_service.py`,
`mp3_manager.py`).

## Part 1 — Save app state on exit, restore on launch

State to persist (SQLite, same `mp3_archive.db` the library already uses):

| Key            | Meaning                                                |
|----------------|--------------------------------------------------------|
| `play_mode`    | last play mode (`sequential`/`repeat_one`/…)           |
| `shuffle_seed` | current shuffle seed (so the random order survives)    |
| `theme`        | `system` / `light` / `dark`                            |
| `view_mode`    | 목록 tab view (`details`/`list`/`tree`/`tiles`/`table`) |
| `show_art`     | whether the 재생 tab album art is visible              |
| `queue_source` | `.list` file the queue was loaded from (else empty)    |
| `now_path`     | path of the track that was playing/paused on exit      |
| `now_index`    | its queue index                                        |
| `now_pos`      | playback position in seconds at exit                   |

Queue persistence:
- New `play_queue` table (ordered paths) + `app_state` key/value table in
  `Mp3Manager` (`set_state`/`get_state`/`save_queue`/`load_queue`).
- If the queue came verbatim from a `.list` file (loaded into an empty queue
  or via "교체"), only `queue_source` is stored and the file is re-read on
  launch; any queue edit clears `queue_source` and the rows are stored
  instead.

Lifecycle:
- `_save_app_state()` runs in `on_pause` and `on_stop` (Android may kill the
  process without `on_stop`).
- Prefs (`theme`, `view_mode`, `show_art`, `play_mode`, `shuffle_seed`) are
  restored in `__init__` so `build()` applies the theme; the queue and the
  paused track are restored in `on_start` (`_restore_session()`).
- The restored track is shown **paused** at the saved position; pressing play
  resumes that track from there (the `sync` IPC command gains an optional
  `position` field so the service seeks right after loading).

## Part 2 — Deterministic seeded shuffle

Replace the pick-anything-random shuffle with a fixed random order:

- `playlist.shuffle_order(count, seed)` — deterministic permutation of
  `range(count)` (a `random.Random(seed)` shuffle).
- `playlist.advance(current, count, mode, seed, ended)` /
  `playlist.retreat(current, count, mode, seed)` — single entry points for
  next/prev in every mode; both return `(index, seed)`. For shuffle they walk
  the permutation, so:
  1. The seed (and thus the order) never changes while the queue is unchanged.
  2. Next/prev follow the fixed order both ways (prev wraps to the end).
  3. No track index repeats until the whole order has been played once.
  4. When the order is exhausted, a fresh seed is generated (avoiding an
     immediate repeat of the last track) and a new order begins.
  5. Duplicate paths occupy distinct indices, so duplicates may each play.
- Reseed triggers in the UI: any queue mutation (add/remove/clear/load) and
  re-entering shuffle via the mode button.
- The seed travels in the `sync` command (UI → service) and in every state
  snapshot (service → UI) so both processes walk the same order; whichever
  side exhausts the cycle reseeds and the other adopts it.
- `next_index`/`prev_index` lose their rng-based shuffle branch (all callers
  now use `advance`/`retreat`).

## Test updates (same commits as the code)

- `test_playlist.py`: seeded-order determinism, full-cycle no-repeat,
  exhaustion reseed, prev wrap, duplicate indices, non-shuffle passthrough;
  drop the old rng-injection shuffle tests.
- `test_service_ipc.py`: `seed`/`position` in `sync`, `seed` in state.
- `test_mp3_manager.py`: `app_state` and `play_queue` round-trips.
- `test_main_window_android.py`: save/restore helpers exercised with a stub
  app + in-memory `Mp3Manager` (skipped off-device like the other Kivy tests).

## Out of scope

- The desktop PyQt app (`main_window.py`) keeps its own QSettings/theme code.
- On-device APK verification cannot run in this environment (no adb/gh CLI);
  the routine in CLAUDE.md must be run after the branch is pushed.
