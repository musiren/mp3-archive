# Android Feature Parity with the Desktop (PyQt6) App

Goal: bring the Android (KivyMD) app to feature parity with the desktop
(`main_window.py`) app. The shared backend (`mp3_manager.py`,
`itunes_fetcher.py`, `tag_fetcher.py`, lyrics helpers) is pure Python and
reused as-is; only the UI layer differs.

## Feature inventory

| # | Desktop feature | Android status | KivyMD approach |
|---|-----------------|----------------|-----------------|
| 1 | Pick directory + scan | ✅ done (MDFileManager) | — |
| 2 | Incremental scan + progress | ✅ done | — |
| 3 | **Full (force) rescan** | ❌ | toolbar overflow menu item → `scan(force=True)` |
| 4 | **Search (filename / all tags)** | ❌ | `MDTextField` search bar + toggle on 목록 tab → `manager.search()` |
| 5 | Delete selected | ✅ done | — |
| 6 | Table with columns (album, genre, year, duration, size, dates) | partial (2-line rows) | richer row + a detail view |
| 7 | **Tree view (path hierarchy) + toggle** | ❌ | optional; `MDExpansionPanel`/nested lists (low priority on mobile) |
| 8 | Column show/hide/reorder | ❌ | N/A on mobile — **skip** |
| 9 | **Playlist / queue** (add, reorder, remove, clear) | ❌ | in-memory queue + a queue screen; reorder via up/down buttons |
| 10 | **Save / Load .list** | ❌ | write/read newline path file under app storage or chosen dir |
| 11 | **Prev / Next** | ❌ | player-tab buttons honoring play mode |
| 12 | **Seek** | ❌ (read-only bar) | interactive `MDSlider` with an update guard |
| 13 | **Volume** | ❌ | `MDSlider` → `sound.volume` |
| 14 | **Play modes** (sequential / repeat_one / repeat_all / shuffle) | ❌ | cycle button; drives auto-advance |
| 15 | Auto-advance at track end per mode | ❌ | hook into the position poll / `sound.on_stop` |
| 16 | **Album art** | ❌ | `_get_album_art` (port from desktop) → `Image`/texture on player tab |
| 17 | **Lyrics** | ❌ | `_get_lyrics` (exists) → label/section on player tab |
| 18 | **자세히 (tag detail view/edit)** | ❌ | `MDDialog` with `MDTextField`s → `manager.update_tags()` |
| 19 | **태그 찾기 (iTunes fetch)** | ❌ | dialog listing `itunes_fetcher`/`tag_fetcher` candidates → apply |
| 20 | **인터넷에서 정보 보기 (song info)** | ❌ | read-only info dialog from the same fetchers |
| 21 | **Theme toggle (light/dark)** | ❌ (light only) | `theme_cls.theme_style` toggle in overflow menu |
| 22 | **About (version from NEWS)** | ❌ | `MDDialog` reading the NEWS version |
| 23 | Per-directory DB (`.mp3-archive.db`) | ❌ (single app-storage DB) | keep single DB on Android (simpler); revisit if needed |

## Interaction differences (touch vs desktop)

- No right-click → use **long-press** or a per-row trailing **⋮ menu** for
  자세히 / 가사 / 태그 찾기 / 재생목록에 추가.
- No drag-drop reorder → **up/down buttons** in the queue screen.
- Row tap currently plays immediately; with a queue, tap should **enqueue +
  play**, and a long-press menu offers "재생목록에 추가" without playing.

## Phased delivery (each phase = one build/test cycle)

**Phase 1 — Complete the player** (highest value; builds on the 재생 tab)
queue model, prev/next, seek, volume, play modes, auto-advance, album art,
lyrics. Row tap enqueues + plays.

**Phase 2 — Library** search bar (filename/tags), full rescan, richer rows,
count/status label.

**Phase 3 — Metadata dialogs** 자세히 (edit), 태그 찾기 (iTunes), 인터넷
정보, 가사 — reusing the existing pure-Python fetchers.

**Phase 4 — App polish** theme toggle, About, save/load playlist, optional
tree view.

## Testing constraint

Kivy will not install on the host (Python 3.14); all KivyMD code is verified
only by CI build + on-device run. Pure helpers (time/format/art-extraction/
search-arg logic) get unit tests that run in CI. Therefore deliver in phases
and validate each on-device before starting the next.
