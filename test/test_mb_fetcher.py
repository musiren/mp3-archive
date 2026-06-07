"""
test_mb_fetcher.py - Unit tests for src/mb_fetcher.py.

The MusicBrainz WS/2 JSON web service is replaced with unittest.mock so the
tests run fully offline with no network access or rate-limiting concerns.
Assertions mirror test_tag_fetcher.py so the urllib reimplementation keeps
the exact same candidate-dict shape as the musicbrainzngs-based fetcher.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch
from urllib.parse import unquote_plus

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import mb_fetcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeResponse:
    """A minimal stand-in for the urlopen() context manager."""

    def __init__(self, payload: bytes):
        """Store the byte payload that read() will return."""
        self._payload = payload

    def read(self) -> bytes:
        """Return the canned response body."""
        return self._payload

    def __enter__(self):
        """Enter the context manager, returning self."""
        return self

    def __exit__(self, *args) -> bool:
        """Exit the context manager without suppressing exceptions."""
        return False


def _mb_json(recordings: list) -> bytes:
    """Encode a WS/2 JSON response envelope around the given recordings."""
    return json.dumps({"recordings": recordings}).encode("utf-8")


def _recording(title, artist, album="", date="2020", score=95, mb_id="abc-123"):
    """Build a minimal WS/2 JSON recording dict."""
    return {
        "id": mb_id,
        "title": title,
        "score": score,
        "artist-credit": [{"name": artist, "joinphrase": ""}],
        "releases": [{"title": album, "date": date}],
    }


def _release(title, date="2020", primary_type=""):
    """Build a WS/2 JSON release dict including its release-group primary-type."""
    rel = {"title": title, "date": date}
    if primary_type:
        rel["release-group"] = {"primary-type": primary_type}
    return rel


def _capture(recordings):
    """
    Return (side_effect, captured) for patching urlopen.

    The side_effect records the requested URL into *captured* and returns a
    fake response wrapping the given recordings as WS/2 JSON.
    """
    captured = {}

    def _side_effect(req, *args, **kwargs):
        captured["url"] = req.full_url
        return _FakeResponse(_mb_json(recordings))

    return _side_effect, captured


# ---------------------------------------------------------------------------
# mb_fetcher.search()
# ---------------------------------------------------------------------------

class TestMbFetcherSearch(unittest.TestCase):
    """Tests for the dependency-free MusicBrainz search()."""

    def test_returns_empty_when_no_args(self):
        """Verify search() returns [] when both artist and title are None."""
        self.assertEqual(mb_fetcher.search(None, None), [])

    def test_returns_candidates_on_success(self):
        """Verify search() parses the WS/2 JSON envelope into candidate dicts."""
        side, _ = _capture([
            _recording("Bohemian Rhapsody", "Queen",
                       "A Night at the Opera", "1975", 98),
        ])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search("Queen", "Bohemian Rhapsody")

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["mb_id"],  "abc-123")
        self.assertEqual(r["title"],  "Bohemian Rhapsody")
        self.assertEqual(r["artist"], "Queen")
        self.assertEqual(r["album"],  "A Night at the Opera")
        self.assertEqual(r["year"],   "1975")
        self.assertEqual(r["score"],  98)

    def test_returns_empty_on_network_error(self):
        """Verify search() returns [] when urlopen raises an exception."""
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            self.assertEqual(mb_fetcher.search("Artist", "Title"), [])

    def test_records_last_error_on_failure(self):
        """Verify search() records the exception repr in last_error on failure."""
        with patch("urllib.request.urlopen", side_effect=Exception("boom")):
            mb_fetcher.search("Artist", "Title")
        self.assertIn("boom", mb_fetcher.last_error)

    def test_clears_last_error_on_success(self):
        """Verify a successful search clears any previous last_error."""
        mb_fetcher.last_error = "stale"
        side, _ = _capture([_recording("Song", "Artist")])
        with patch("urllib.request.urlopen", side_effect=side):
            mb_fetcher.search("Artist", "Song")
        self.assertEqual(mb_fetcher.last_error, "")

    def test_score_field_is_integer(self):
        """Verify score is coerced to int even when given as a string."""
        side, _ = _capture([_recording("Song", "Artist", score="87")])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search("Artist", "Song")
        self.assertIsInstance(results[0]["score"], int)
        self.assertEqual(results[0]["score"], 87)

    def test_year_truncated_to_four_digits(self):
        """Verify only the four-digit year of the release date is returned."""
        side, _ = _capture([_recording("Song", "Artist", date="2005-03-15")])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search("Artist", "Song")
        self.assertEqual(results[0]["year"], "2005")

    def test_release_missing_returns_empty_album(self):
        """Verify a recording without releases yields an empty album field."""
        rec = _recording("Song", "Artist")
        rec["releases"] = []
        side, _ = _capture([rec])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search("Artist", "Song")
        self.assertEqual(results[0]["album"], "")
        self.assertEqual(results[0]["year"], "")

    def test_artist_credit_phrase_joined(self):
        """Verify multi-artist credits are joined using their joinphrase."""
        rec = _recording("Collab", "")
        rec["artist-credit"] = [
            {"name": "Artist A", "joinphrase": " feat. "},
            {"name": "Artist B", "joinphrase": ""},
        ]
        side, _ = _capture([rec])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search(None, "Collab")
        self.assertEqual(results[0]["artist"], "Artist A feat. Artist B")

    def test_query_contains_both_clauses_and_limit(self):
        """Verify the request URL carries recording:, artist: and the limit."""
        side, captured = _capture([_recording("Song", "Artist")])
        with patch("urllib.request.urlopen", side_effect=side):
            mb_fetcher.search("Artist", "Song", limit=5)
        decoded = unquote_plus(captured["url"])
        self.assertIn('recording:"Song"', decoded)
        self.assertIn('artist:"Artist"', decoded)
        self.assertIn("fmt=json", captured["url"])
        self.assertIn("limit=5", captured["url"])

    def test_search_with_title_only(self):
        """Verify search() builds a title-only query when artist is None."""
        side, captured = _capture([_recording("Mystery Song", "Unknown")])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search(None, "Mystery Song")
        decoded = unquote_plus(captured["url"])
        self.assertIn('recording:"Mystery Song"', decoded)
        self.assertNotIn('artist:"', decoded)
        self.assertEqual(results[0]["title"], "Mystery Song")

    def test_length_formatted_as_minutes_seconds(self):
        """Verify the WS/2 ``length`` (ms) is formatted as ``M:SS``."""
        rec = _recording("Song", "Artist")
        rec["length"] = 355000  # 5:55
        side, _ = _capture([rec])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search("Artist", "Song")
        self.assertEqual(results[0]["length"], "5:55")

    def test_length_empty_when_missing_or_invalid(self):
        """Verify length is "" when the field is missing, None, or non-numeric."""
        for raw in (None, "", "abc", 0, -1):
            rec = _recording("Song", "Artist")
            if raw is not None:
                rec["length"] = raw
            side, _ = _capture([rec])
            with patch("urllib.request.urlopen", side_effect=side):
                results = mb_fetcher.search("Artist", "Song")
            self.assertEqual(results[0]["length"], "", f"raw={raw!r}")

    def test_disambiguation_is_returned(self):
        """Verify the recording's ``disambiguation`` qualifier is surfaced."""
        rec = _recording("Song", "Artist")
        rec["disambiguation"] = "live, Wembley 1986"
        side, _ = _capture([rec])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search("Artist", "Song")
        self.assertEqual(results[0]["disambiguation"], "live, Wembley 1986")

    def test_disambiguation_defaults_to_empty(self):
        """Verify disambiguation is "" when absent or null in the WS/2 JSON."""
        side, _ = _capture([_recording("Song", "Artist")])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search("Artist", "Song")
        self.assertEqual(results[0]["disambiguation"], "")

    def test_releases_summary_includes_every_release(self):
        """Verify ``releases`` lists every release with title, year, and type."""
        rec = _recording("Song", "Artist")
        rec["releases"] = [
            _release("Studio Album", "1975-11-21", "Album"),
            _release("Greatest Hits", "1981", "Compilation"),
            _release("Live Tour", "1992-04-01", "Live"),
        ]
        side, _ = _capture([rec])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search("Artist", "Song")
        releases = results[0]["releases"]
        self.assertEqual(len(releases), 3)
        self.assertEqual(releases[0], {"title": "Studio Album", "year": "1975", "type": "Album"})
        self.assertEqual(releases[1], {"title": "Greatest Hits", "year": "1981", "type": "Compilation"})
        self.assertEqual(releases[2], {"title": "Live Tour", "year": "1992", "type": "Live"})

    def test_releases_summary_tolerates_missing_release_group(self):
        """Verify a release without ``release-group`` yields an empty type."""
        rec = _recording("Song", "Artist")
        rec["releases"] = [_release("Bootleg", "1980")]  # no primary_type
        side, _ = _capture([rec])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search("Artist", "Song")
        self.assertEqual(results[0]["releases"][0]["type"], "")

    def test_releases_summary_empty_when_no_releases(self):
        """Verify recordings with no releases produce an empty ``releases`` list."""
        rec = _recording("Song", "Artist")
        rec["releases"] = []
        side, _ = _capture([rec])
        with patch("urllib.request.urlopen", side_effect=side):
            results = mb_fetcher.search("Artist", "Song")
        self.assertEqual(results[0]["releases"], [])


if __name__ == "__main__":
    unittest.main()
