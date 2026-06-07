"""
itunes_fetcher.py - iTunes Search API metadata lookup.

Searches the iTunes catalog by artist and/or title and returns a ranked list
of candidate tracks.  Particularly useful for Korean music which may not be
well-covered by MusicBrainz.

Example:
    from itunes_fetcher import search
    candidates = search(artist="BTS", title="Dynamite")
    for c in candidates:
        print(c["title"], c["artist"], c["album"])
"""

import json
import urllib.parse
import urllib.request

from net_util import ssl_context

# Set to the repr() of the last network/parse exception (cleared on each call).
last_error = ""


def search(
    artist: str | None,
    title: str | None,
    limit: int = 7,
    country: str = "KR",
) -> list[dict]:
    """
    Search the iTunes catalog by artist and/or title.

    Uses the public iTunes Search API (no API key required).

    Args:
        artist:  Artist name to search for (may be None).
        title:   Track title to search for (may be None).
        limit:   Maximum number of results to return.
        country: iTunes store country code (default: "KR" for Korea).

    Returns:
        List of candidate dicts with keys:
          title, artist, album, year, score, artwork_url.
        Returns an empty list if neither artist nor title is provided,
        or if the network request fails.
    """
    global last_error
    last_error = ""

    parts = []
    if artist:
        parts.append(artist)
    if title:
        parts.append(title)

    if not parts:
        return []

    term = " ".join(parts)
    params = urllib.parse.urlencode({
        "term":    term,
        "country": country,
        "media":   "music",
        "entity":  "song",
        "limit":   limit,
    })
    url = f"https://itunes.apple.com/search?{params}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mp3-archive/1.0"})
        with urllib.request.urlopen(req, timeout=10, context=ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        # Record so the UI can distinguish a TLS/network failure from a
        # genuine no-match result.
        last_error = repr(exc)
        return []

    results = data.get("results", [])
    total = len(results)
    candidates = []
    for i, item in enumerate(results):
        # Assign a descending score so the first iTunes result ranks highest.
        score = 100 - i * (100 // max(total, 1))
        release_date = item.get("releaseDate", "") or ""
        year = release_date[:4] if release_date else ""
        candidates.append({
            "title":       item.get("trackName", ""),
            "artist":      item.get("artistName", ""),
            "album":       item.get("collectionName", ""),
            "year":        year,
            "score":       max(score, 0),
            "artwork_url": item.get("artworkUrl100", ""),
        })

    return candidates
