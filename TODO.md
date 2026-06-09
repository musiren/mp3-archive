# TODO

## Status

Desktop ↔ Android feature parity is essentially complete: the Android (KivyMD)
app now covers scanning, search, five view modes (목록 / 자세히 / 트리 / 타일 /
표), online metadata, full tag editing, the playlist/queue subsystem, the player
controls (with the volume slider driving the system media volume), a
home-screen player widget, and **background playback** (foreground service:
keeps playing backgrounded / screen-off, queue + auto-advance owned by the
service, audio focus, and notification + lock-screen media controls). Verified
on-device (Galaxy SM-S928N).

## Android — follow-ups / nice-to-have

- **Persist UI state across launches** — sort mode, theme, and view mode are
  kept in memory only (volume now follows the system media volume, which the OS
  persists). Persisting the **last scanned folder** would also keep the 트리
  view and the tree-folder "재생목록에 추가" working after a relaunch without
  re-scanning (today `_last_dir` resets to None).
- **Rebuild the UI queue after a cold restart** — if the OS fully kills the UI
  process while the service keeps playing, the relaunched UI shows an empty
  queue (playback continues). Have the service push its queue on resume so the
  UI can rebuild it.
- **Queue reorder (deferred)** — the user wants to drag queue rows to reorder,
  but KivyMD's RecycleView has no built-in drag-reorder (recycled widgets need
  a ghost-overlay drag). Decide between a true drag implementation and simpler
  up/down move actions in the queue row's long-press menu.
- **Local-fallback seek is best-effort** — when the background service is
  unavailable the SoundLoader fallback's `get_pos()` returns 0 and `seek()` may
  be ignored. The service path uses `android.media.MediaPlayer`, whose `seekTo`
  works.

## Shared / backend

- Consider migrating the desktop app from `tag_fetcher` (musicbrainzngs) to the
  dependency-free `mb_fetcher`, so there is a single MusicBrainz implementation.

## Not planned (desktop-only affordances, intentionally dropped on touch)

- Keyboard shortcuts and the menu bar.
- The multi-column reorderable/hideable desktop table (replaced by the 표 view).
- Mouse-hover album-art tooltips.
