# Android: Table (표) View Mode

Add a fifth list view mode, **표 (table)**, alongside 목록 / 자세히 / 트리 / 타일.
It shows the library as a multi-column tag table with:

- **Selectable columns** — the user picks which tags to show.
- **Per-column sort** — tapping a column header sorts by it; tapping again
  toggles ascending/descending (▲/▼ indicator).
- **Horizontal scroll** — many columns will not fit the phone width, so the
  header + rows scroll horizontally together.

The existing 자세히 (album-art card) view is kept unchanged; the table is a
separate mode (user's choice).

## Pure logic — `src/table_util.py` (locally tested)

GUI-independent so it runs under unittest without Kivy:

- `available_columns()` → list of `(key, label, width_dp, numeric)` defs.
  Columns come from the DB row fields (no per-row file reads): filename, title,
  artist, album, genre, year, duration, filesize, comment, file_modified_at.
- `DEFAULT_COLUMNS` = title / artist / album / genre / year / duration.
- `format_cell(key, value)` → display string (duration → M:SS, filesize →
  B/KB/MB, None → "").
- `row_values(file_info, column_keys)` → list of formatted cell strings.
- `sort_files_by(files, key, reverse)` → numeric sort for duration/filesize,
  case-insensitive text otherwise; **missing values always last** in both
  directions (split present/missing, sort present, append missing).
- `next_sort(cur_key, cur_reverse, tapped_key)` → `(key, reverse)` header-tap
  state machine (same key toggles reverse, new key resets to ascending).
- `toggle_column(selected, key)` → add/remove a column, result re-ordered to
  the canonical definition order.
- `header_label(key, sort_key, reverse)` → label with a ▲/▼ suffix when sorted.

## UI — `src/main_window_android.py`

- 보기 menu gains **표**; `_view_mode == "table"`.
- New KV: a horizontal `ScrollView` (do_scroll_x only) wrapping a vertical box
  of `[table_header][table_rv]`, both width = sum of selected column widths, so
  header and the (vertically-virtualized) RecycleView scroll horizontally as
  one. New `TableRow` viewclass = a horizontal box of fixed-width cell labels,
  rebuilt from row data; header cells are sort buttons.
- `_apply_view_mode` shows `mp3_table` and hides `mp3_list` / `mp3_grid` for
  the table mode; `_refresh_list` builds header + RV data (sorted via
  `sort_files_by`) when in table mode.
- Column selection via a ⋮-overflow **표 컬럼** dialog of checkboxes (only
  relevant in table mode); applying rebuilds the table.
- State: `_table_columns` (selected keys), `_table_sort_key`,
  `_table_sort_reverse` — in memory (matches the existing in-memory view mode).

## Testing
Local: `table_util` under unittest (format, sort incl. missing-last + reverse,
toggle, next_sort, header_label). On-device: scan
`/storage/emulated/0/MyMusic/Single`, switch to 표, toggle columns, sort by a
column both directions, and scroll horizontally — screenshots as evidence.
