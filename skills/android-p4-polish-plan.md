# Android P4 — Tag Detail + Polish

Finish the P4 "tag detail + polish" basket from the feature-parity plan. Each
numbered item ships as its own commit; all touch the Android app, so they share
one CI build + on-device verification at the end (push once).

Pure, GUI-independent logic is factored into small modules with local unit
tests (Kivy will not import on the host); the KivyMD wiring is verified only by
the on-device run. New shared helper module: `src/ui_util.py` (sort / theme /
version), tested in `test/test_ui_util.py`. Stream-info and all-tags helpers go
in `src/audio_meta.py`.

## Items (one commit each)

1. **#17 Sort menu** — `ui_util.sort_files(files, mode)` for
   name / artist / title / date(file_modified_at), case-insensitive, missing
   values sort last. Android: a 정렬 entry that opens a dropdown; `_sort_mode`
   in memory; sort applied in `_refresh_list` before assigning RV data.
2. **#18 Theme toggle** — `ui_util.resolve_theme_style(choice, device_is_dark)`
   → "Light"/"Dark" (choice ∈ system/light/dark). Android: 테마 dropdown sets
   `theme_cls.theme_style`; "system" reads the device night mode via jnius
   (best-effort, Light off-device).
3. **#19 About dialog** — `ui_util.latest_news_version(news_text)` parses the
   first `vYYYYMMDD (date)` header from NEWS. Android: an 정보 dialog showing
   the app title + version (read NEWS bundled next to the sources).
4. **#14 File + stream info** — `audio_meta.get_stream_info(path)` →
   {sample_rate, channels, bitrate, length}; `audio_meta.format_summary_rows`
   builds (label, value) display rows from a file-info dict + stream info.
   Android: read-only summary rows in the 자세히 dialog (size / duration /
   created / modified / samplerate / channels / bitrate).
5. **#13 Full tag table** — `audio_meta.read_all_tags(path)` → list of
   (label, value, easy_key) for every easy tag, Korean labels. Android: render
   all tags in the 자세히 dialog as editable fields (beyond the current six),
   saved via `update_tags`.
6. **#16 Incremental scan** — Android `_scan_worker` stops calling `clear()`
   before every scan, so a folder pick merges into the library and skips
   unchanged files (scan already supports this); the refresh button keeps
   `force=True` (re-read + prune stale under that directory).

## Out of scope / already done
- #15 (album art in 자세히) already shipped.
- Cross-launch persistence of sort/theme/view-mode is a later follow-up; these
  stay in memory for now (matches the existing in-memory view-mode).

## Testing
Local: `ui_util`, `audio_meta` helpers under unittest. On-device: scan
`/storage/emulated/0/MyMusic/Single` (per CLAUDE.md) and exercise each of the
six on the phone with screenshots.
