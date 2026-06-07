"""
table_util.py - Pure helpers for the Android 표 (table) view mode.

GUI-independent so the column model, cell formatting, sorting, and
header/column-selection state can be unit-tested locally without Kivy. The
front-end (main_window_android) renders the columns; all the decisions live
here.
"""

# Column definitions: (key, label, width_dp, numeric). ``key`` is the DB row
# field (so no per-row file reads are needed), ``label`` the Korean header,
# ``width_dp`` the cell width, and ``numeric`` whether it sorts numerically.
_COLUMNS = [
    ("filename",         "파일명", 220, False),
    ("title",            "제목",   190, False),
    ("artist",           "아티스트", 150, False),
    ("album",            "앨범",   180, False),
    ("genre",            "장르",   110, False),
    ("year",             "년도",    72, False),
    ("duration",         "길이",    72, True),
    ("filesize",         "크기",    96, True),
    ("comment",          "코멘트",  180, False),
    ("file_modified_at", "수정일", 160, False),
]

# Columns shown by default until the user customises the selection.
DEFAULT_COLUMNS = ["title", "artist", "album", "genre", "year", "duration"]

# key -> (label, width, numeric) for O(1) lookups.
_BY_KEY = {key: (label, width, numeric)
           for key, label, width, numeric in _COLUMNS}


def available_columns() -> list:
    """Return the column definitions as a list of (key, label, width, numeric)."""
    return list(_COLUMNS)


def column_label(key: str) -> str:
    """Return the Korean header label for a column key (or the key itself)."""
    entry = _BY_KEY.get(key)
    return entry[0] if entry else key


def column_width(key: str) -> int:
    """Return the display width (in dp units) for a column key."""
    entry = _BY_KEY.get(key)
    return entry[1] if entry else 120


def is_numeric_column(key: str) -> bool:
    """Return whether a column sorts numerically (e.g. duration, filesize)."""
    entry = _BY_KEY.get(key)
    return bool(entry and entry[2])


def _fmt_duration(seconds) -> str:
    """Format a duration in seconds as 'M:SS'; '' when missing or non-positive."""
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    return f"{total // 60}:{total % 60:02d}"


def _fmt_size(num) -> str:
    """Format a byte count as B / KB / MB; '' when missing."""
    try:
        num = int(num)
    except (TypeError, ValueError):
        return ""
    if num < 0:
        return ""
    if num < 1024:
        return f"{num} B"
    if num < 1024 ** 2:
        return f"{num / 1024:.1f} KB"
    return f"{num / 1024 ** 2:.1f} MB"


def format_cell(key: str, value) -> str:
    """
    Format a raw DB value for display in a table cell.

    Args:
        key:   The column key the value belongs to.
        value: The raw value from the file-info row.

    Returns:
        A display string: duration as 'M:SS', filesize as B/KB/MB, anything
        else stringified ('' for None).
    """
    if key == "duration":
        return _fmt_duration(value)
    if key == "filesize":
        return _fmt_size(value)
    return "" if value is None else str(value)


def row_values(file_info: dict, column_keys: list) -> list:
    """
    Return the formatted cell strings for one row across the given columns.

    Args:
        file_info:   A DB row dict (Mp3Manager.list_files()/search()).
        column_keys: The ordered keys of the columns to render.

    Returns:
        A list of display strings, one per column key.
    """
    return [format_cell(key, file_info.get(key)) for key in column_keys]


def sort_files_by(files: list, key: str, reverse: bool = False) -> list:
    """
    Sort file-info dicts by an arbitrary column key.

    Numeric columns (duration, filesize) sort numerically; others sort
    case-insensitively as text. Rows missing the value are always placed last,
    regardless of direction, so toggling ascending/descending never buries the
    populated rows beneath blanks.

    Args:
        files:   Row dicts to sort.
        key:     The column key to sort on.
        reverse: True for descending order among the populated rows.

    Returns:
        A new sorted list (the input is never mutated).
    """
    numeric = is_numeric_column(key)
    present = []
    missing = []
    for f in files:
        value = f.get(key)
        if numeric:
            try:
                present.append((float(value), f))
            except (TypeError, ValueError):
                missing.append(f)
        else:
            text = str(value).strip() if value is not None else ""
            if text in ("", "-"):
                missing.append(f)
            else:
                present.append((text.casefold(), f))
    present.sort(key=lambda pair: pair[0], reverse=reverse)
    return [f for _, f in present] + missing


def next_sort(current_key, current_reverse: bool, tapped_key: str) -> tuple:
    """
    Compute the next sort state after a column header is tapped.

    Args:
        current_key:     The currently-sorted column key, or None.
        current_reverse: Whether the current sort is descending.
        tapped_key:      The header the user just tapped.

    Returns:
        A ``(key, reverse)`` tuple: tapping the active column toggles the
        direction; tapping a different column sorts it ascending.
    """
    if current_key == tapped_key:
        return (tapped_key, not current_reverse)
    return (tapped_key, False)


def toggle_column(selected: list, key: str) -> list:
    """
    Add or remove a column from the selection, keeping definition order.

    Args:
        selected: The currently-selected column keys.
        key:      The column key to toggle.

    Returns:
        A new list of selected keys ordered to match available_columns(), so
        columns always appear in a consistent order regardless of toggle order.
    """
    chosen = set(selected)
    if key in chosen:
        chosen.discard(key)
    else:
        chosen.add(key)
    return [k for k, *_ in _COLUMNS if k in chosen]


def header_label(key: str, sort_key, reverse: bool) -> str:
    """
    Return a column header label, with a sort-direction arrow when active.

    Args:
        key:      The column the header is for.
        sort_key: The currently-sorted column key, or None.
        reverse:  Whether the active sort is descending.

    Returns:
        The Korean label, suffixed with " ▼" (descending) or " ▲" (ascending)
        when this column is the active sort key.
    """
    label = column_label(key)
    if key == sort_key:
        return f"{label} {'▼' if reverse else '▲'}"
    return label
