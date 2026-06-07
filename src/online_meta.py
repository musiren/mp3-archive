"""
online_meta.py - Pure helpers for online metadata lookups.

GUI-independent glue between an audio file's stored tags and the network
fetchers (mb_fetcher / itunes_fetcher). Deliberately free of Kivy/PyQt imports
so the query-building, source-merging, and batch-queue logic can be unit-tested
locally without a UI.
"""

import os

# Source identifiers passed to fetch_candidates(). The string values match the
# desktop tag_fetch_dialog so the two front-ends behave identically.
SOURCE_MB = "musicbrainz"
SOURCE_ITUNES = "itunes"
SOURCE_BOTH = "both"

# (label, identifier) pairs for the UI source selector. iTunes is listed first
# because it is the default — it has noticeably better Korean-catalogue
# coverage than MusicBrainz, which is the common case for this library.
SOURCE_LABELS = (
    ("iTunes", SOURCE_ITUNES),
    ("MusicBrainz", SOURCE_MB),
    ("둘 다", SOURCE_BOTH),
)


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


def merge_candidates(mb_results: list, itunes_results: list) -> list:
    """
    Merge MusicBrainz and iTunes candidate lists into one ranked list.

    Each candidate is tagged with a human-readable ``source`` ("MusicBrainz"
    or "iTunes") so the UI can show where every row came from, and the combined
    list is sorted by descending score so the best matches — regardless of
    source — appear first.

    Args:
        mb_results:     Candidate dicts from mb_fetcher.search (may be empty).
        itunes_results: Candidate dicts from itunes_fetcher.search (may be empty).

    Returns:
        A new list of candidate dicts (shallow copies, never the inputs) each
        carrying a ``source`` key, ordered by ``score`` descending.
    """
    merged = []
    for cand in mb_results or []:
        item = dict(cand)
        item.setdefault("source", "MusicBrainz")
        merged.append(item)
    for cand in itunes_results or []:
        item = dict(cand)
        item.setdefault("source", "iTunes")
        merged.append(item)
    merged.sort(key=lambda c: c.get("score", 0), reverse=True)
    return merged


def fetch_candidates(
    artist: str | None,
    title: str | None,
    source: str = SOURCE_ITUNES,
    mb=None,
    itunes=None,
) -> list:
    """
    Search one or both online sources and return merged, ranked candidates.

    Pure glue around the two fetchers: *source* decides which one(s) to query,
    the fetchers are injectable so the merge logic can be unit-tested offline,
    and the results are combined by merge_candidates(). Never raises — each
    fetcher already swallows network errors and returns [] (recording its own
    module-level ``last_error`` for the UI to surface).

    Args:
        artist: Artist query term (may be None).
        title:  Title query term (may be None).
        source: One of SOURCE_MB, SOURCE_ITUNES, SOURCE_BOTH.
        mb:     MusicBrainz search callable; defaults to mb_fetcher.search.
        itunes: iTunes search callable; defaults to itunes_fetcher.search.

    Returns:
        A merged, score-sorted list of candidate dicts (empty when neither
        source returns anything or neither is selected).
    """
    if mb is None:
        from mb_fetcher import search as mb
    if itunes is None:
        from itunes_fetcher import search as itunes

    mb_results = mb(artist, title) if source in (SOURCE_MB, SOURCE_BOTH) else []
    itunes_results = (
        itunes(artist, title) if source in (SOURCE_ITUNES, SOURCE_BOTH) else []
    )
    return merge_candidates(mb_results, itunes_results)


def _missing_core_tag(info: dict) -> bool:
    """
    Return True when a file is missing its title or artist tag.

    Args:
        info: A row dict with optional "title"/"artist" keys.

    Returns:
        True if either field is empty or the "-" placeholder (so the file is
        worth auto-completing), False when both hold a real value.
    """
    return (clean_query_field(info.get("title")) is None
            or clean_query_field(info.get("artist")) is None)


class TagFetchQueue:
    """
    Step-through queue of files for the batch tag auto-completion flow.

    Mirrors the desktop TagFetchDialog's queue: by default it holds only files
    missing a core tag (title or artist), since those are the ones worth
    auto-completing; pass ``force=True`` to process every file. The UI walks
    the queue one file at a time — applying or skipping each — and reads the
    counter, current file, and fallback search terms from here, so all the
    bookkeeping stays in one GUI-independent, locally-tested place.
    """

    def __init__(self, files: list, force: bool = False) -> None:
        """
        Build the queue from a list of file-info dicts.

        Args:
            files: Row dicts as returned by Mp3Manager.list_files().
            force: When True keep every file; otherwise keep only files whose
                   title or artist tag is missing (None, "", or the "-"
                   placeholder).
        """
        if force:
            self._files = list(files)
        else:
            self._files = [f for f in files if _missing_core_tag(f)]
        self._index = 0
        self._applied = 0

    def is_done(self) -> bool:
        """Return True once every queued file has been applied or skipped."""
        return self._index >= len(self._files)

    def total(self) -> int:
        """Return the number of files in the queue."""
        return len(self._files)

    def position(self) -> int:
        """Return the 1-based index of the current file (total+1 when done)."""
        return self._index + 1

    def counter_text(self) -> str:
        """Return the ``(current / total)`` progress label for the header."""
        return f"({self.position()} / {self.total()})"

    def current(self) -> dict | None:
        """Return the current file-info dict, or None when the queue is done."""
        if self.is_done():
            return None
        return self._files[self._index]

    def advance(self) -> None:
        """Move to the next file without recording an application (a skip)."""
        self._index += 1

    def mark_applied(self) -> None:
        """Record that the current file's tags were applied and advance."""
        self._applied += 1
        self._index += 1

    def applied_count(self) -> int:
        """Return how many files have had tags applied so far."""
        return self._applied

    def auto_retry_keyword(self) -> str:
        """
        Return the current file's name without extension, for a fallback search.

        When a tag-based search returns nothing, retrying with the bare
        filename often succeeds; this provides that keyword. Empty when the
        queue is done.
        """
        f = self.current()
        if not f:
            return ""
        return os.path.splitext(f.get("filename", "") or "")[0]

    def query_terms(self) -> tuple:
        """
        Return the (artist, title) search terms for the current file.

        Uses the file's cleaned artist/title; when both are missing it falls
        back to the filename stem as the title so there is always something to
        search. Returns (None, None) when the queue is done.
        """
        f = self.current()
        if not f:
            return (None, None)
        artist, title = build_song_query(f)
        if not artist and not title:
            title = self.auto_retry_keyword() or None
        return (artist, title)
