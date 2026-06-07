# Android Feature Parity with the Desktop (PyQt6) App

Goal: bring the Android (KivyMD) app to feature parity with the desktop
(`main_window.py`) app. The shared backend (`mp3_manager.py`,
`itunes_fetcher.py`, `tag_fetcher.py`, `audio_meta.py`, `tree_util.py`) is pure
Python and reused as-is; only the UI layer differs.

> Status as of 2026-06-07, reconciled against a full source-to-source audit of
> `main_window.py` + dialogs vs `main_window_android.py`. The core daily
> workflow (scan / search / four view modes / playback / tag edit / lyrics) is
> done; the remaining work is the playlist/queue subsystem and online metadata.

## Already ported (✅ done, verified on device)

- Pick directory + scan (MDFileManager) with progress bar + status label.
- **Full (force) rescan** — toolbar refresh button → `scan(force=True)`.
- **Search** by filename, with a "태그 포함" toggle for all-tag search;
  debounced for the Korean IME; clear-search button; "전체/검색 N곡" count.
- **Delete selected** records (DB only; files stay on disk) with confirmation.
- **Four view modes** — 목록 (compact) / 자세히 (2-line + album art) / 트리
  (folder hierarchy, expand/collapse) / 타일 (album-art grid). Selector in the
  toolbar 보기 menu. (Richer than desktop, which has no tile grid.)
- **Album art** extraction + per-path file cache, shown in 자세히 rows + tiles.
- **자세히 (tag detail edit)** dialog — edit title/artist/album/genre/year/
  comment, save to file + DB.
- **가사 (lyrics)** dialog — embedded lyrics with mojibake/line-ending repair.
- **Per-row long-press actions** (자세히 / 가사) in list, details, tile **and
  tree** views.
- Playback basics: tap to play, **play/pause/stop**, elapsed/total time labels,
  a position bar (read-only), now-playing title/subtitle.
- **Incremental scan** — picking a folder merges into the library and skips
  unchanged files (by mtime); the refresh button forces a full re-read and
  prunes records for files missing under that directory.
- **Sort menu** (이름/아티스트/제목/날짜) and **theme toggle** (시스템/라이트/
  다크) and **About dialog** in the ⋮ overflow menu.
- **자세히 dialog** also shows read-only file/stream info (size, duration,
  dates, samplerate, channels, bitrate) and edits every embedded easy-tag.

## Remaining work (prioritized)

### 🔴 P1 — Playlist / queue subsystem (largest; features are interdependent)

| # | Feature | Desktop behavior | Effort |
|---|---------|------------------|--------|
| 1 | **Queue model** | persistent playlist; tap/drag to enqueue, remove, clear | large |
| 2 | Auto-advance at track end | next track per play mode when a sound ends | medium |
| 3 | **Prev / Next** buttons | move within the queue | small (needs queue) |
| 4 | **Play modes** | sequential / repeat-one / repeat-all / shuffle cycle | medium |
| 5 | **Save / Load `.list`** | newline path file; skip missing on load | medium |
| 6 | Now-playing row highlight | bold/colored row for the playing track | small (needs queue) |

KivyMD approach: in-memory queue backed by a RecycleView; reorder via up/down
buttons (no touch drag-reorder in KivyMD RV); row tap = enqueue + play, while
long-press keeps the "재생목록에 추가" (add-without-play) action.

### ✅ P2 — Online metadata (done; on-device verification pending for #8/#9)

`mb_fetcher.py` / `itunes_fetcher.py` are pure Python; the `INTERNET`
permission and a network daemon thread are wired up. All three features ship.

| # | Feature | Desktop behavior | Status |
|---|---------|------------------|--------|
| 7 | **Single-song info (MusicBrainz)** + apply | up to 7 ranked candidates → apply to file+DB | ✅ done (+ per-candidate diff) |
| 8 | **Source select + keyword override** | MusicBrainz / iTunes / both dropdown + manual search terms | ✅ done |
| 9 | **Batch tag auto-completion** | step through files missing title/artist; fetch, show ranked candidates, apply/skip | ✅ done |

### 🟡 P3 — Player controls + player-tab richness (mostly small)

| # | Feature | Current Android | Effort |
|---|---------|-----------------|--------|
| 10 | **Volume** | none | small (MDSlider → `sound.volume`) |
| 11 | **Interactive seek** | position bar is read-only | small (MDSlider → `sound.seek()`; provider caveat) |
| 12 | **Lyrics + album art on the 재생 tab** | only via long-press dialogs | medium |

### ✅ P4 — Tag detail + polish (done; on-device verification pending)

| # | Feature | Status |
|---|---------|--------|
| 13 | Full tag table — edit every embedded easy-tag, not just six | ✅ done |
| 14 | File summary + stream info rows in 자세히 | ✅ done |
| 15 | Album-art thumbnail in 자세히 dialog | ✅ done (earlier) |
| 16 | **Incremental scan** — merge + skip-unchanged; refresh prunes | ✅ done |
| 17 | **Sort menu** (name / artist / title / date) | ✅ done |
| 18 | **Theme toggle** (system/light/dark) | ✅ done |
| 19 | **About dialog** (version from NEWS) | ✅ done |

## Not applicable on touch (skip — no user-facing gap on phones)

Keyboard shortcuts, the menu bar, multi-column sortable/reorderable/hideable
table, and mouse-hover album-art tooltips. The underlying *actions* (theme,
about, playlist save/load) are captured above; only the desktop UI affordances
are dropped.

## Interaction differences (touch vs desktop)

- No right-click → **long-press** opens the per-row actions menu (자세히 / 가사,
  later 재생목록에 추가 / 태그 찾기). Already wired in all view modes.
- No drag-drop reorder → **up/down buttons** in the queue screen.
- Row tap currently plays immediately; once a queue exists, tap should
  **enqueue + play**, and long-press offers "재생목록에 추가" without playing.

## Testing constraint

Kivy will not install on the host (Python 3.14; PyQt6 also segfaults under a
full `unittest discover`), so KivyMD code is verified by CI build + on-device
run. Pure helpers (`audio_meta`, `tree_util`, `mp3_manager`, time/format/search
logic) get unit tests that run locally and in CI. Deliver in phases and
validate each on-device before starting the next.
