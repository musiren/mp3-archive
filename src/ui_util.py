"""
ui_util.py - Pure, GUI-independent helpers for the app's UI chrome.

Collects small decision/formatting helpers used by the front-ends (sorting the
file list, resolving a theme choice, reading the app version) so the logic can
be unit-tested locally without importing Kivy or PyQt.
"""

import re


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


def resolve_theme_style(choice: str, device_is_dark: bool = False) -> str:
    """
    Resolve a theme *choice* to a KivyMD ``theme_style`` value.

    Args:
        choice:         "light", "dark", or "system" (follow the device).
        device_is_dark: Whether the device is currently in night mode; only
                        consulted when *choice* is "system".

    Returns:
        "Dark" or "Light" — the string KivyMD's ``theme_cls.theme_style``
        expects. An explicit light/dark choice wins; "system" (or any
        unrecognised value) follows the device, defaulting to "Light".
    """
    if choice == "dark":
        return "Dark"
    if choice == "light":
        return "Light"
    return "Dark" if device_is_dark else "Light"


def latest_news_version(news_text: str | None) -> str:
    """
    Extract the most recent release version from NEWS file text.

    The NEWS file lists releases newest-first under ``vYYYYMMDD (date)``
    headers; this returns the first such version token found.

    Args:
        news_text: The full text of the NEWS file (may be None/empty).

    Returns:
        The first ``vYYYYMMDD`` token (e.g. "v20260420"), or "" when the text
        is empty or contains no recognisable version header.
    """
    for line in (news_text or "").splitlines():
        match = re.match(r"\s*(v\d{6,8})\b", line)
        if match:
            return match.group(1)
    return ""
