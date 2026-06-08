# TODO

## Status

Desktop ↔ Android feature parity is essentially complete: the Android (KivyMD)
app now covers scanning, search, five view modes (목록 / 자세히 / 트리 / 타일 /
표), online metadata, full tag editing, the playlist/queue subsystem, and the
player controls. It is verified on-device (Galaxy SM-S928N) except auto-advance,
whose logic is unit-tested but was not wall-clock-observed.

## Android — follow-ups / nice-to-have

- **Persist UI state across launches** — sort mode, theme, view mode, and
  volume are kept in memory only. Persisting the **last scanned folder** would
  also keep the 트리 view and the tree-folder "재생목록에 추가" working after a
  relaunch without re-scanning (today `_last_dir` resets to None).
- **Queue reorder** — add up/down buttons per queue row (KivyMD's RecycleView
  has no touch drag-reorder).
- **Interactive seek is best-effort** — the Android audio provider's `get_pos()`
  returns 0 (elapsed time is tracked manually) and `seek()` may be ignored;
  revisit if a provider with working seek is adopted.
- **Wall-clock verify auto-advance** on-device (logic is unit-tested).

## Shared / backend

- Consider migrating the desktop app from `tag_fetcher` (musicbrainzngs) to the
  dependency-free `mb_fetcher`, so there is a single MusicBrainz implementation.

## Not planned (desktop-only affordances, intentionally dropped on touch)

- Keyboard shortcuts and the menu bar.
- The multi-column reorderable/hideable desktop table (replaced by the 표 view).
- Mouse-hover album-art tooltips.
