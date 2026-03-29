"""
tag_fetcher.py - MusicBrainz metadata lookup for MP3 files.

Searches the MusicBrainz database by artist and/or title and
returns a ranked list of candidate recordings.

Example:
    from tag_fetcher import search
    candidates = search(artist="Queen", title="Bohemian Rhapsody")
    for c in candidates:
        print(c["title"], c["artist"], c["album"])
"""

import musicbrainzngs

# Identify this application to the MusicBrainz API as required by their ToS.
musicbrainzngs.set_useragent(
    "mp3-archive", "1.0", "https://github.com/musiren/mp3-archive"
)


def search(
    artist: str | None,
    title: str | None,
    limit: int = 7,
) -> list[dict]:
    """
    Search MusicBrainz recordings by artist and/or title.

    Builds a Lucene query from the provided fields and returns
    the top matches ranked by score (highest first).

    Args:
        artist: Artist name to search for (may be None).
        title:  Recording title to search for (may be None).
        limit:  Maximum number of candidates to return.

    Returns:
        List of candidate dicts with keys:
          mb_id, title, artist, album, year, score.
        Returns an empty list if neither artist nor title is provided,
        or if the network request fails.
    """
    parts = []
    if title:
        parts.append(f'recording:"{title}"')
    if artist:
        parts.append(f'artist:"{artist}"')

    if not parts:
        return []

    try:
        result = musicbrainzngs.search_recordings(
            query=" AND ".join(parts), limit=limit
        )
    except Exception:
        return []

    candidates = []
    for rec in result.get("recording-list", []):
        releases = rec.get("release-list", [])
        release = releases[0] if releases else {}
        candidates.append({
            "mb_id":  rec.get("id", ""),
            "title":  rec.get("title", ""),
            "artist": rec.get("artist-credit-phrase", ""),
            "album":  release.get("title", ""),
            "year":   (release.get("date", "") or "")[:4],
            "score":  int(rec.get("ext:score", 0)),
        })

    return candidates
