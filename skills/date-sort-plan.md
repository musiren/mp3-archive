# Plan: Make the 날짜 (date) Sort Order Every Song

Target: the Android UI (`src/main_window_android.py`) plus the shared helpers
`src/ui_util.py` and `src/mp3_manager.py`.

## Report

Sorting the list by 날짜 only ordered part of it: the songs received the day
before came first in date order, and every other song stayed in name order.
The 표 (table) view also seemed to ignore the sort menu, and the chosen sort
did not survive a restart (the phone reboots nightly).

## Causes

1. **The sort key is too fragile.** `ui_util.sort_files(.., "date")` orders by
   `file_modified_at` alone. A song whose key is empty (a row with no stored
   date) or identical to its neighbours (a bulk copy, or a transfer that left
   the epoch placeholder, 1970-01-01, as the mtime) compares equal to all of
   them, and Python's stable sort leaves those songs in the database order,
   which is `ORDER BY artist, title` — name order. Only songs with a real,
   distinct modified time (the ones received yesterday) end up sorted.
2. **표 view ignores the sort menu.** `_build_table` only applies the column
   the user last tapped (`_table_sort_key`, `None` by default), so the menu's
   choice is silently dropped there.
3. **The sort mode is never saved.** `_sort_mode` starts as `"artist"` on every
   launch, unlike the theme, view mode and the other preferences.
4. **The tree orders folders by one date and files by another** (folders by the
   newest `file_created_at`, files by `file_modified_at`), so the tree looks
   half sorted.

## Design

### 1. A sturdier date key (`ui_util.file_date_key`)

The key is the later of the file's modified and created timestamps, ignoring
values before 1990 (placeholders such as the epoch). On Android the created
timestamp is the inode change time, which a copy or download sets to when the
file arrived and a transfer cannot preserve, so the sort follows "when did
this land on the phone, or was last changed" even when the source's old
modified time survived the copy. A file with no usable timestamp has the key
"" and still sorts last. `sort_files(.., "date")` and the tree's folder order
both use it, so the two agree.

This changes what 날짜 means for a file copied with its original (older)
modified time: it now follows when it arrived. That matches how the sort is
used ("what did I receive recently").

### 2. Fill in dates the database lacks (`Mp3Manager.fill_missing_dates`)

Rows with no stored date (scanned before the columns existed and never
rescanned) are read from disk in one transaction and updated, once per
library per session and only when the sort is 날짜. Capped per call so a huge
library cannot stall the UI thread; the remainder fills on the next refresh.

### 3. Table view follows the menu

`_ordered_table_files` applies the tapped column when there is one, else the
menu's sort. Choosing a sort from the menu clears the tapped column so the
menu's choice takes effect.

### 4. Persist the sort mode

`_set_sort_mode` and `_save_app_state` store `sort_mode`; `__init__` restores
it with `_restore_pref`, validated against the four known modes.

## Test updates (same commits as the code)

- `test_ui_util.py`: `file_date_key` (later of the two, placeholders and empty
  values ignored), date sort falling back to the created time for songs with an
  epoch or empty modified time, ties keeping their order.
- `test_mp3_manager.py`: `fill_missing_dates` fills only missing values from a
  real file, leaves existing values, skips vanished files, honours the cap.
- `test_main_window_android.py`: `_ordered_table_files`, `_set_sort_mode`
  (persists, clears the tapped column), `_save_app_state` stores the mode,
  `_ensure_dates_filled` runs once per manager and only for 날짜.

## Out of scope

- Showing the date on each row, so the order can be checked by eye.
- The desktop app (`main_window.py`) has its own table sorting.
- On-device verification cannot run here (no adb): after the branch is built,
  pick 날짜, check that older songs now follow a date order, kill the app and
  reopen it, and check the sort is still 날짜.
