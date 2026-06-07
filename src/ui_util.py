"""
ui_util.py - Pure, GUI-independent helpers for the app's UI chrome.

Collects small decision/formatting helpers used by the front-ends (sorting the
file list, resolving a theme choice, reading the app version) so the logic can
be unit-tested locally without importing Kivy or PyQt.
"""


def _text_sort_key(value: str | None) -> tuple:
    """
    Build a case-insensitive sort key that pushes missing values to the end.

    Args:
        value: A tag/field value (may be None, empty, or the "-" placeholder
               the list uses for a missing tag).

    Returns:
        A ``(group, text)`` tuple: group 0 for real values (sorted by their
        case-folded text) and group 1 for missing values, so blanks always
        sort after real entries regardless of direction.
    """
    text = (value or "").strip()
    if text in ("", "-"):
        return (1, "")
    return (0, text.casefold())


def sort_files(files: list, mode: str) -> list:
    """
    Return a new list of file-info dicts sorted by the given mode.

    Args:
        files: Row dicts as returned by Mp3Manager.list_files()/search().
        mode:  One of "name" (filename), "artist" (then title), "title", or
               "date" (file_modified_at, newest first). Any other value
               leaves the order unchanged.

    Returns:
        A new sorted list (the input is never mutated). Text sorts are
        case-insensitive with missing values last; "date" sorts newest first
        with undated files last.
    """
    items = list(files)
    if mode == "name":
        return sorted(items, key=lambda f: _text_sort_key(f.get("filename")))
    if mode == "artist":
        return sorted(items, key=lambda f: (_text_sort_key(f.get("artist")),
                                            _text_sort_key(f.get("title"))))
    if mode == "title":
        return sorted(items, key=lambda f: _text_sort_key(f.get("title")))
    if mode == "date":
        # ISO-8601 strings sort chronologically; reverse = newest first, which
        # also drops undated ("") entries to the end.
        return sorted(items, key=lambda f: (f.get("file_modified_at") or ""),
                      reverse=True)
    return items
