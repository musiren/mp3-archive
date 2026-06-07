# Android: Online Metadata (P2)

Port the desktop online-metadata features to the Android (KivyMD) app:

1. **Single-song online info** (MusicBrainz) → up to ~7 ranked candidates →
   apply to file + DB.
2. **Source selection** (MusicBrainz / iTunes / 둘 다) + manual keyword
   override.
3. **Batch tag auto-completion** stepping through files missing title/artist.

## Key decisions

- **No new buildozer requirements.** `musicbrainzngs` (used by the desktop
  `tag_fetcher.py`) is intentionally NOT added — it has no python-for-android
  recipe, so bundling it risks the APK build. Instead the MusicBrainz search is
  reimplemented over stdlib `urllib` in a new pure module `mb_fetcher.py` with
  the identical return shape. `itunes_fetcher.py` is already stdlib-only and is
  reused as-is.
- **buildozer.spec:** add `INTERNET` to `android.permissions` (normal,
  install-time, no runtime prompt). `requirements` is unchanged.
- **Threading:** every network search runs on a daemon thread (reuse the
  scan-worker pattern) and marshals results back via `Clock.schedule_once` /
  `@mainthread`; `urlopen` has a 10 s timeout and must never block the Kivy
  main thread.
- **Apply path:** `Mp3Manager.update_file_tags(path, title, artist, album)`
  (src/mp3_manager.py) already writes file + DB; it writes only non-None
  title/artist/album (no genre/year), matching the desktop dialogs exactly.

## Return shapes (consumed directly by the UI)

- `mb_fetcher.search(artist, title, limit=7)` →
  `[{mb_id, title, artist, album, year, score}]` (same as `tag_fetcher.search`).
- `itunes_fetcher.search(artist, title, limit=7, country="KR")` →
  `[{title, artist, album, year, score, artwork_url}]`.

## Phases (one build + on-device test each)

### Phase 0 — `mb_fetcher.py` (pure, no GUI) — **done first**
- New `src/mb_fetcher.py`: urllib GET to
  `https://musicbrainz.org/ws/2/recording?query=<lucene>&fmt=json&limit=N`
  with the required descriptive `User-Agent`, 10 s timeout, JSON parse, `[]` on
  any error. Lucene query identical to `tag_fetcher` (`recording:".." AND
  artist:".."`). Rebuilds the artist-credit phrase from `artist-credit[]`.
- `buildozer.spec`: add `INTERNET`.
- New `test/test_mb_fetcher.py`: fully-mocked `urlopen`; mirrors
  `test_tag_fetcher.py` assertions (shape, score→int, year[:4], empty album,
  artist-credit join, query clauses + limit). Runs locally.
- First on-device APK also validates HTTPS/SSL works under p4a.

### Phase 1 — single-song online info dialog (MusicBrainz) + apply
- Add an `온라인 정보` button to the per-row long-press actions menu
  (next to 자세히/가사).
- Custom `MDDialog` (`type="custom"`, like `_open_detail`/`_open_lyrics`):
  read-only current tags at top, indeterminate `MDProgressBar` + status label,
  a `RecycleView` of `CandidateRow` items (제목 / 아티스트·앨범·연도 / 점수),
  first row auto-selected, buttons `태그 적용` + `닫기`.
- Search on a daemon thread; apply via `update_file_tags`; refresh list.
- Factor `_build_song_query(file_info) -> (artist, title)` (value unless blank
  or "-", else None) as a pure, locally-tested helper.

### Phase 2 — source selection + keyword override
- Shared `fetch_candidates(artist, title, source)` worker (source ∈
  {musicbrainz, itunes, both}); tag each candidate with `source`; merge + sort
  by score desc. Default source **iTunes** (better Korean coverage).
- Add an `MDDropdownMenu` source selector (reuse the 보기-menu pattern) + an
  `MDTextField` keyword override with a 검색 button. Show 출처 per candidate.
- Factor `merge_candidates(mb, itunes)` and `fetch_candidates(..., mb=,
  itunes=)` (injectable fetchers) as pure helpers; unit-test offline.

### Phase 3 — batch tag auto-completion (step-through queue)
- Toolbar/menu action `태그 자동 완성`: queue = `list_files()` filtered to
  files missing title/artist (per-file long-press `태그 찾기` forces all).
- Step through one file at a time reusing the Phase 1/2 content + a `(M / N)`
  counter and 파일 label; auto-search; auto-retry with the filename stem when a
  search returns nothing; `적용` / `건너뛰기`; completion summary.
- Factor a pure `TagFetchQueue` helper (filter / current / advance / is_done /
  counter / `auto_retry_keyword` / applied_count); unit-test offline.

## Risks

- **p4a SSL:** HTTPS to musicbrainz.org / itunes.apple.com needs the python3
  recipe's `_ssl` + CA certs (shipped in p4a v2024.01.21). Validate on the
  first on-device run — if missing, both fetchers silently return `[]`
  (looks like "no results").
- **Silent failure UX:** fetchers swallow all exceptions → `[]`. Consider a
  distinct `네트워크 오류` status so offline ≠ no-match.
- **MusicBrainz rate limit:** ~1 req/sec, requires the User-Agent. Human-paced
  step-through keeps batch under the limit; never auto-advance searches.
- **Two MB implementations** (desktop musicbrainzngs vs Android mb_fetcher):
  mitigate by identical return shape + mirrored tests; optionally migrate the
  desktop to mb_fetcher later.

## Testing constraint

Kivy/PyQt6 do not run locally, so UI wiring is verified by CI build + on-device
only. All non-UI logic (fetchers, query building, merge/sort, queue) is
factored into pure helpers with local unit tests.
