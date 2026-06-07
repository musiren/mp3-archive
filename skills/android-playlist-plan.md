# Android P1 — Playlist / Queue Subsystem

Port the desktop playlist/queue to the Android (KivyMD) app. Delivered in small
commits; pure logic is unit-tested locally, KivyMD UI is verified on-device.
Each user action must fire exactly once (no double play / double advance).

## Pure logic — `src/playlist.py` (locally tested)

- `PLAY_MODES = ["sequential", "repeat_one", "repeat_all", "shuffle"]`.
- `next_play_mode(mode)` → cycles to the next mode.
- `next_index(current, count, mode, ended=False, rng=None)` → next index, or
  `None` to stop. sequential: `current+1` (None past last when `ended`, else
  clamp to last for the Next button); repeat_one: `current`; repeat_all:
  `(current+1) % count`; shuffle: `rng.randrange(count)`.
- `prev_index(current, count, mode, rng=None)` → mirror of next for the Prev
  button (sequential clamps at 0; repeat_all wraps; shuffle random).
- `serialize_playlist(paths)` / `parse_playlist(text)` → `.list` is one absolute
  path per line; parse drops blanks (the UI skips missing files via os.path).
- `class PlayQueue`: `items`, `current_index`, `current_item`, `add(item)`,
  `add_many`, `remove(i)`, `clear()`, `set_current(i)`, `__len__`, `is_empty`.
  Items are file-info dicts (path/filename/artist/title) so the queue row can
  display and play. Removing shifts `current_index` correctly.

`rng` is injectable so shuffle is testable deterministically.

## UI — `src/main_window_android.py` (on-device)

Commits (small, in order):

1. **playlist.py + tests** — the pure module above.
2. **Queue model + play-from-queue** — `self._queue = PlayQueue()`; 목록 row
   **tap = enqueue + play** (switch to 재생), long-press gains **재생목록에
   추가** (enqueue without playing). `_play` records the playing path so the
   queue can highlight it. Guard the existing `_suppress_next_play` so a
   long-press never also enqueues/plays (action-fires-once).
3. **Queue list on the 재생 tab + now-playing highlight (#1, #6)** — a
   RecycleView of queued tracks below the controls; tap a row → play that
   index; a remove (✕) button per row; the playing row is highlighted. A
   `QueueRow` viewclass.
4. **Prev / Next buttons (#3)** — ⏮/⏭ in the transport row → `prev_index` /
   `next_index(ended=False)`.
5. **Play modes (#4)** — a mode button cycling 순차/한곡반복/전체반복/셔플
   (icon per mode) via `next_play_mode`.
6. **Auto-advance (#2)** — when a track ends (`_update_position` sees state ≠
   "play"), advance via `next_index(ended=True)` instead of stopping; stop only
   when it returns None. Must advance exactly once per end.
7. **Save / Load `.list` (#5)** — ⋮ or queue-area buttons: save via
   `serialize_playlist` to a file in the music dir; load via the file manager →
   `parse_playlist` → skip missing → enqueue. Reuse MDFileManager.

## Reorder
Up/down buttons per queue row (KivyMD RV has no touch drag-reorder). Optional;
add if time permits (small).

## Testing
Local: `playlist` under unittest (modes, next/prev incl. ended/clamp/wrap,
shuffle via injected rng, serialize/parse, PlayQueue add/remove/current-shift).
On-device: scan `/storage/emulated/0/MyMusic/Single`, enqueue, play through,
prev/next, each mode, auto-advance, save/load — screenshots as evidence.
