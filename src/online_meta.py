"""
online_meta.py - Pure helpers for online metadata lookups.

GUI-independent glue between an audio file's stored tags and the network
fetchers (mb_fetcher / itunes_fetcher). Deliberately free of Kivy/PyQt imports
so the query-building (and, later, result-merging) logic can be unit-tested
locally without a UI.
"""


def clean_query_field(value: str | None) -> str | None:
    """
    Normalise a stored tag value for use as a search term.

    Args:
        value: A stored tag value (may be None).

    Returns:
        The trimmed value, or None when it is empty or the "-" placeholder
        the list uses for missing tags (so it never pollutes the query).
    """
    if not value:
        return None
    value = value.strip()
    if not value or value == "-":
        return None
    return value


def build_song_query(info: dict) -> tuple:
    """
    Build (artist, title) search terms from a track's stored tag info.

    Mirrors the desktop SongInfoDialog: a field is used only when it holds a
    real value, otherwise None so the Lucene query is built from what's known.

    Args:
        info: A mapping with optional "artist" and "title" keys.

    Returns:
        An (artist, title) tuple where each element is the cleaned value or None.
    """
    return (clean_query_field(info.get("artist")),
            clean_query_field(info.get("title")))
