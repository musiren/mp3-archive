"""
test_itunes_fetcher.py - Unit tests for src/itunes_fetcher.py.

All HTTP calls are replaced with unittest.mock so tests run offline.
"""

import io
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import itunes_fetcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_response(results: list[dict]) -> MagicMock:
    """Return a mock context-manager whose read() yields a JSON-encoded response."""
    body = json.dumps({"resultCount": len(results), "results": results}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _track(
    name="Song",
    artist="Artist",
    album="Album",
    date="2020-01-01T00:00:00Z",
    artwork="https://example.com/art100x100bb.jpg",
) -> dict:
    """Build a minimal iTunes search result item."""
    return {
        "trackName":       name,
        "artistName":      artist,
        "collectionName":  album,
        "releaseDate":     date,
        "artworkUrl100":   artwork,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestItunesFetcherSearch(unittest.TestCase):

    def test_returns_empty_when_no_args(self):
        """search() returns [] when both artist and title are None."""
        result = itunes_fetcher.search(None, None)
        self.assertEqual(result, [])

    def test_returns_candidates_on_success(self):
        """search() parses iTunes results into candidate dicts."""
        fake = _fake_response([_track("Dynamite", "BTS", "BE", "2020-08-21T07:00:00Z")])
        with patch("urllib.request.urlopen", return_value=fake):
            results = itunes_fetcher.search("BTS", "Dynamite")

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["title"],  "Dynamite")
        self.assertEqual(r["artist"], "BTS")
        self.assertEqual(r["album"],  "BE")
        self.assertEqual(r["year"],   "2020")

    def test_year_extracted_from_date(self):
        """search() extracts the 4-digit year from releaseDate."""
        fake = _fake_response([_track(date="1999-12-31T00:00:00Z")])
        with patch("urllib.request.urlopen", return_value=fake):
            results = itunes_fetcher.search("Artist", "Title")
        self.assertEqual(results[0]["year"], "1999")

    def test_artwork_url_present(self):
        """search() includes artwork_url in every candidate."""
        url = "https://example.com/art100x100bb.jpg"
        fake = _fake_response([_track(artwork=url)])
        with patch("urllib.request.urlopen", return_value=fake):
            results = itunes_fetcher.search("Artist", "Title")
        self.assertEqual(results[0]["artwork_url"], url)

    def test_returns_empty_on_network_error(self):
        """search() returns [] when the HTTP request raises an exception."""
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = itunes_fetcher.search("Artist", "Title")
        self.assertEqual(result, [])

    def test_score_descending(self):
        """First result gets a higher score than subsequent results."""
        items = [_track(f"Song {i}") for i in range(3)]
        fake = _fake_response(items)
        with patch("urllib.request.urlopen", return_value=fake):
            results = itunes_fetcher.search("Artist", "Song")
        self.assertGreater(results[0]["score"], results[1]["score"])
        self.assertGreater(results[1]["score"], results[2]["score"])

    def test_search_with_artist_only(self):
        """search() works when only artist is provided."""
        fake = _fake_response([_track("Hit Song", "Solo Artist")])
        with patch("urllib.request.urlopen", return_value=fake):
            results = itunes_fetcher.search("Solo Artist", None)
        self.assertEqual(len(results), 1)

    def test_search_with_title_only(self):
        """search() works when only title is provided."""
        fake = _fake_response([_track("Mystery Song")])
        with patch("urllib.request.urlopen", return_value=fake):
            results = itunes_fetcher.search(None, "Mystery Song")
        self.assertEqual(len(results), 1)

    def test_missing_release_date_yields_empty_year(self):
        """search() returns empty year string when releaseDate is absent."""
        item = _track()
        del item["releaseDate"]
        fake = _fake_response([item])
        with patch("urllib.request.urlopen", return_value=fake):
            results = itunes_fetcher.search("Artist", "Title")
        self.assertEqual(results[0]["year"], "")

    def test_empty_results_from_api(self):
        """search() returns [] when the API returns zero results."""
        fake = _fake_response([])
        with patch("urllib.request.urlopen", return_value=fake):
            results = itunes_fetcher.search("Nobody", "Nonexistent")
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
