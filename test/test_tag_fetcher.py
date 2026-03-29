"""
test_tag_fetcher.py - Unit tests for src/tag_fetcher.py and
Mp3Manager.update_file_tags().

MusicBrainz network calls are replaced with unittest.mock so tests
run offline without rate-limiting concerns.
"""

import os
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mp3_manager import Mp3Manager, _create_table, _save_to_db
import tag_fetcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_manager() -> Mp3Manager:
    """Return an Mp3Manager backed by an in-memory SQLite database."""
    mgr = Mp3Manager.__new__(Mp3Manager)
    mgr._conn = sqlite3.connect(":memory:", check_same_thread=False)
    _create_table(mgr._conn)
    return mgr


def _mb_response(recordings: list[dict]) -> dict:
    """Wrap a list of recording dicts in a MusicBrainz response envelope."""
    return {"recording-list": recordings}


def _recording(title, artist, album="", date="2020", score=95, mb_id="abc-123"):
    """Build a minimal MusicBrainz recording dict."""
    return {
        "id": mb_id,
        "title": title,
        "artist-credit-phrase": artist,
        "ext:score": str(score),
        "release-list": [{"title": album, "date": date}],
    }


# ---------------------------------------------------------------------------
# tag_fetcher.search()
# ---------------------------------------------------------------------------

class TestTagFetcherSearch(unittest.TestCase):

    def test_returns_empty_when_no_args(self):
        """Verify that search() returns [] when both artist and title are None."""
        result = tag_fetcher.search(None, None)
        self.assertEqual(result, [])

    def test_returns_candidates_on_success(self):
        """Verify that search() parses MusicBrainz results into dicts."""
        fake = _mb_response([
            _recording("Bohemian Rhapsody", "Queen", "A Night at the Opera", "1975", 98),
        ])
        with patch("musicbrainzngs.search_recordings", return_value=fake):
            results = tag_fetcher.search("Queen", "Bohemian Rhapsody")

        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r["title"],  "Bohemian Rhapsody")
        self.assertEqual(r["artist"], "Queen")
        self.assertEqual(r["album"],  "A Night at the Opera")
        self.assertEqual(r["year"],   "1975")
        self.assertEqual(r["score"],  98)

    def test_returns_empty_on_network_error(self):
        """Verify that search() returns [] when MusicBrainz raises an exception."""
        with patch("musicbrainzngs.search_recordings", side_effect=Exception("timeout")):
            result = tag_fetcher.search("Artist", "Title")
        self.assertEqual(result, [])

    def test_score_field_is_integer(self):
        """Verify that the score field is returned as an int."""
        fake = _mb_response([_recording("Song", "Artist", score=87)])
        with patch("musicbrainzngs.search_recordings", return_value=fake):
            results = tag_fetcher.search("Artist", "Song")
        self.assertIsInstance(results[0]["score"], int)

    def test_year_truncated_to_four_digits(self):
        """Verify that only the year portion of the date is returned."""
        fake = _mb_response([_recording("Song", "Artist", date="2005-03-15")])
        with patch("musicbrainzngs.search_recordings", return_value=fake):
            results = tag_fetcher.search("Artist", "Song")
        self.assertEqual(results[0]["year"], "2005")

    def test_release_missing_returns_empty_album(self):
        """Verify that a recording without releases has an empty album field."""
        rec = _recording("Song", "Artist")
        rec["release-list"] = []
        fake = _mb_response([rec])
        with patch("musicbrainzngs.search_recordings", return_value=fake):
            results = tag_fetcher.search("Artist", "Song")
        self.assertEqual(results[0]["album"], "")

    def test_search_with_title_only(self):
        """Verify that search() works when only title is provided."""
        fake = _mb_response([_recording("Mystery Song", "Unknown")])
        with patch("musicbrainzngs.search_recordings", return_value=fake) as mock_fn:
            tag_fetcher.search(None, "Mystery Song")
        call_kwargs = mock_fn.call_args
        self.assertIn("Mystery Song", str(call_kwargs))


# ---------------------------------------------------------------------------
# Mp3Manager.update_file_tags()
# ---------------------------------------------------------------------------

class TestUpdateFileTags(unittest.TestCase):

    def _make_mp3(self, tmpdir: str, filename: str = "track.mp3") -> str:
        """Create an empty file that acts as a stub MP3 (no real audio data)."""
        path = os.path.join(tmpdir, filename)
        open(path, "wb").close()
        return path

    def test_updates_db_title(self):
        """Verify that update_file_tags() updates the title in the database."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._make_mp3(tmpdir)
            _save_to_db(mgr._conn, {
                "path": path, "filename": "track.mp3",
                "title": None, "artist": None, "album": None,
                "genre": None, "year": None, "comment": None,
                "duration": None, "filesize": 0,
                "file_created_at": None, "file_modified_at": None,
            })
            mgr.update_file_tags(path, title="New Title", artist=None, album=None)
            row = mgr.list_files()[0]
        self.assertEqual(row["title"], "New Title")
        mgr.close()

    def test_updates_db_artist_and_album(self):
        """Verify that artist and album are updated independently."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._make_mp3(tmpdir)
            _save_to_db(mgr._conn, {
                "path": path, "filename": "track.mp3",
                "title": "Old Title", "artist": None, "album": None,
                "genre": None, "year": None, "comment": None,
                "duration": None, "filesize": 0,
                "file_created_at": None, "file_modified_at": None,
            })
            mgr.update_file_tags(path, title=None, artist="New Artist", album="New Album")
            row = mgr.list_files()[0]
        self.assertEqual(row["title"],  "Old Title")   # unchanged
        self.assertEqual(row["artist"], "New Artist")
        self.assertEqual(row["album"],  "New Album")
        mgr.close()

    def test_none_fields_not_overwritten(self):
        """Verify that passing None leaves existing DB values intact."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._make_mp3(tmpdir)
            _save_to_db(mgr._conn, {
                "path": path, "filename": "track.mp3",
                "title": "Keep Me", "artist": "Keep Artist", "album": "Keep Album",
                "genre": None, "year": None, "comment": None,
                "duration": None, "filesize": 0,
                "file_created_at": None, "file_modified_at": None,
            })
            mgr.update_file_tags(path, title=None, artist=None, album=None)
            row = mgr.list_files()[0]
        self.assertEqual(row["title"],  "Keep Me")
        self.assertEqual(row["artist"], "Keep Artist")
        self.assertEqual(row["album"],  "Keep Album")
        mgr.close()

    def test_missing_file_does_not_raise(self):
        """Verify that update_file_tags() does not raise if the file is gone."""
        mgr = make_manager()
        try:
            mgr.update_file_tags("/nonexistent/path.mp3", "T", "A", "B")
        except Exception as e:
            self.fail(f"update_file_tags raised unexpectedly: {e}")
        mgr.close()


if __name__ == "__main__":
    unittest.main()
