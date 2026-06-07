"""
mb_fetcher.py - Dependency-free MusicBrainz metadata lookup.

A urllib-based reimplementation of ``tag_fetcher.search`` that talks to the
MusicBrainz WS/2 JSON web service directly, with no third-party dependency
(``tag_fetcher.py`` uses the ``musicbrainzngs`` package). This keeps the
Android build's requirement set free of any non-stdlib network library while
returning the identical candidate-dict shape, so the UI can consume either
fetcher interchangeably.

Example:
    from mb_fetcher import search
    candidates = search(artist="Queen", title="Bohemian Rhapsody")
    for c in candidates:
        print(c["title"], c["artist"], c["album"])
"""

import json
import urllib.parse
import urllib.request

from net_util import ssl_context

# MusicBrainz requires a descriptive User-Agent identifying the application
# (requests without one are rejected). See the MusicBrainz API ToS.
_USER_AGENT = "mp3-archive/1.0 ( https://github.com/musiren/mp3-archive )"
_ENDPOINT = "https://musicbrainz.org/ws/2/recording"

# Set to the repr() of the last network/parse exception (cleared on each call),
# so the UI can distinguish a real failure from a genuine no-match result.
last_error = ""


def _artist_phrase(artist_credit: list) -> str:
    """
    Rebuild the full artist-credit phrase from a WS/2 artist-credit list.

    Each credit entry contributes its name plus its trailing joinphrase
    (e.g. " feat. "), reproducing the musicbrainzngs 'artist-credit-phrase'
    used by tag_fetcher so the two fetchers return identical artist strings.

    Args:
        artist_credit: The recording's "artist-credit" list (may be empty).

    Returns:
        The concatenated artist phrase, or "" if the list is empty/invalid.
    """
    parts = []
    for credit in artist_credit or []:
        if isinstance(credit, dict):
            parts.append(credit.get("name", ""))
            parts.append(credit.get("joinphrase", ""))
    return "".join(parts).strip()


def _format_length(length_ms) -> str:
    """
    Convert a MusicBrainz recording length in milliseconds to ``M:SS``.

    The WS/2 ``length`` field is the integer duration in ms (may be missing
    or null for sparsely-tagged recordings). Knowing the duration is one of
    the cheapest ways for a user to tell two takes of the same song apart
    (studio vs. live, edit vs. album version), so the fetcher surfaces it.

    Args:
        length_ms: The raw ``length`` value from a WS/2 recording JSON
                   object — int, str, or None.

    Returns:
        The formatted ``M:SS`` string, or ``""`` if the value is missing,
        non-numeric, or non-positive.
    """
    try:
        ms = int(length_ms)
    except (TypeError, ValueError):
        return ""
    if ms <= 0:
        return ""
    total_sec = ms // 1000
    return f"{total_sec // 60}:{total_sec % 60:02d}"


def _release_summary(releases: list) -> list[dict]:
    """
    Summarise every release a recording appears on for the detail panel.

    A single recording may appear on its original studio album plus any
    number of compilations, live albums, and singles. Returning the full
    list lets the UI show the user all those alternates so they can pick
    the right tagging context (e.g. "use the original 1975 album, not
    the 1981 compilation").

    Args:
        releases: The recording's ``releases`` list from the WS/2 JSON
                  response (may be ``None`` or contain non-dict entries).

    Returns:
        A list of ``{"title", "year", "type"}`` dicts, one per release.
        ``year`` is the 4-digit year (empty if undated). ``type`` is the
        release-group ``primary-type`` (e.g. "Album", "Compilation"),
        empty when the WS/2 response omits it.
    """
    summary = []
    for rel in releases or []:
        if not isinstance(rel, dict):
            continue
        title = rel.get("title", "") or ""
        date = rel.get("date", "") or ""
        rg = rel.get("release-group") or {}
        summary.append({
            "title": title,
            "year":  date[:4] if date else "",
            "type":  rg.get("primary-type", "") or "",
        })
    return summary


def search(
    artist: str | None,
    title: str | None,
    limit: int = 7,
) -> list[dict]:
    """
    Search MusicBrainz recordings by artist and/or title (no dependencies).

    Builds the same Lucene query as ``tag_fetcher.search`` and queries the
    WS/2 JSON web service over stdlib urllib, returning candidates ranked by
    score (highest first).

    Args:
        artist: Artist name to search for (may be None).
        title:  Recording title to search for (may be None).
        limit:  Maximum number of candidates to return.

    Returns:
        List of candidate dicts with keys:
          mb_id, title, artist, album, year, score,
          length, disambiguation, releases.
        ``length`` is the formatted ``M:SS`` duration (empty when unknown),
        ``disambiguation`` is MusicBrainz's free-text qualifier (e.g.
        "live", "acoustic"), and ``releases`` is a list of
        ``{"title", "year", "type"}`` dicts describing every release the
        recording appears on. Returns an empty list if neither artist nor
        title is provided, or if the network request fails.
    """
    parts = []
    if title:
        parts.append(f'recording:"{title}"')
    if artist:
        parts.append(f'artist:"{artist}"')

    global last_error
    last_error = ""

    if not parts:
        return []

    params = urllib.parse.urlencode({
        "query": " AND ".join(parts),
        "fmt":   "json",
        "limit": limit,
    })
    url = f"{_ENDPOINT}?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=10, context=ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        # Record so the UI can distinguish a TLS/network failure from a
        # genuine no-match result (logcat alone is unreliable: p4a buffers
        # daemon-thread stdout).
        last_error = repr(exc)
        return []

    candidates = []
    for rec in data.get("recordings", []):
        releases = rec.get("releases", [])
        release = releases[0] if releases else {}
        try:
            score = int(rec.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        candidates.append({
            "mb_id":          rec.get("id", ""),
            "title":          rec.get("title", ""),
            "artist":         _artist_phrase(rec.get("artist-credit", [])),
            "album":          release.get("title", ""),
            "year":           (release.get("date", "") or "")[:4],
            "score":          score,
            "length":         _format_length(rec.get("length")),
            "disambiguation": rec.get("disambiguation", "") or "",
            "releases":       _release_summary(releases),
        })

    return candidates
