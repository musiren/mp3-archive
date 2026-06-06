# Android: Windows-Explorer-style View Modes + Directory Tree

Add a "보기" (View) selector to the 목록 tab so the file list can be shown as:

- **목록 (List)** — one compact line per song (filename).
- **자세히 (Details)** — two lines (filename + artist — title) **with an album-art
  thumbnail** on the left.
- **트리 (Tree)** — the directory hierarchy under the scanned folder, folders
  expand/collapse, files are leaves.
- **타일 (Tiles)** — grid of album-art tiles. *(deferred to a later build)*

## Decisions (confirmed with the user)

- Text modes first (트리/목록/자세히); 타일 later.
- Album art is shown in the **자세히** view.

## Delivery phases (one build each, verified on device)

**Build 1 — View selector + 목록 + 자세히**
- Toolbar "보기" action opens an `MDDropdownMenu` with 목록 / 자세히.
- The RecycleView swaps its `viewclass` and row height per mode and re-renders
  (`refresh_from_data`); selection state stays in the data so it survives the
  swap, same as the existing list.
- Two recycle viewclasses:
  - `Mp3RowList` = `OneLineAvatarIconListItem` + select icon.
  - `Mp3RowDetails` = `TwoLineAvatarIconListItem` + select icon + a left
    album-art `Image`.
- Album art: `audio_meta.get_album_art()` bytes are written once to a per-app
  cache file (keyed by a path hash) and the row's image `source` points at it;
  missing art falls back to a music glyph. Loading is lazy (only the visible
  rows that RecycleView binds) and guarded so a bad image never crashes a row.
- `self._view_mode` ("list"/"details", default "details").

**Build 2 — 트리 (Tree)**
- Build a nested dict from the scanned files' paths relative to the scan root
  (mirrors the desktop `_fill_tree`).
- Flatten it to a virtualized RecycleView list of indented rows (folder rows
  with ▶/▼, file rows). Tapping a folder toggles expansion and rebuilds the
  flat list; tapping a file plays it. Keeps the list fast for large trees.

**Build 3 (later) — 타일** grid (RecycleGridLayout) of album-art tiles.

## Notes / risks

- KivyMD has no built-in virtualized tree; the flattened-RecycleView approach
  keeps it scalable.
- Album art in a recycled list is the riskiest piece; it is additive (failure
  degrades to a placeholder, never a crash).
- View-mode persistence across launches is a small follow-up (store the mode in
  a settings file); build 1 keeps it in memory, defaulting to 자세히.
