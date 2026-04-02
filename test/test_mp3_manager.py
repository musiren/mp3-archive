"""
test_mp3_manager.py - Unit tests for src/mp3_manager.py (Mp3Manager class).

Tests use an in-memory SQLite database and temporary directories
to avoid side effects on the real filesystem.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mp3_manager import (Mp3Manager, _create_table, _save_to_db, _list_files,
                         _parse_filename_fallback, SUPPORTED_EXTENSIONS)


def make_manager() -> Mp3Manager:
    """Return an Mp3Manager backed by an in-memory SQLite database."""
    mgr = Mp3Manager.__new__(Mp3Manager)
    import sqlite3
    mgr._conn = sqlite3.connect(":memory:")
    _create_table(mgr._conn)
    return mgr


def sample_info(path: str = "/music/test.mp3") -> dict:
    """Return a sample audio info dictionary for testing."""
    return {
        "path": path,
        "filename": os.path.basename(path),
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
        "genre": "Pop",
        "year": "2024",
        "comment": "Test comment",
        "duration": 180.0,
        "filesize": 4096,
        "file_created_at": "2024-01-01 00:00:00",
        "file_modified_at": "2024-06-01 12:00:00",
    }


class TestMp3ManagerContextManager(unittest.TestCase):

    def test_context_manager_closes_connection(self):
        """Verify that the with-block closes the DB connection on exit."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            with Mp3Manager(db_path) as mgr:
                conn = mgr._conn
            # After exit, executing on the closed connection must raise
            with self.assertRaises(Exception):
                conn.execute("SELECT 1")
        finally:
            os.unlink(db_path)


class TestListFiles(unittest.TestCase):

    def test_list_empty_db(self):
        """Verify that list_files returns an empty list for a new database."""
        mgr = make_manager()
        self.assertEqual(mgr.list_files(), [])
        mgr.close()

    def test_list_returns_all_records(self):
        """Verify that list_files returns every inserted record."""
        mgr = make_manager()
        _save_to_db(mgr._conn, sample_info("/music/a.mp3"))
        _save_to_db(mgr._conn, sample_info("/music/b.mp3"))
        self.assertEqual(len(mgr.list_files()), 2)
        mgr.close()

    def test_list_returns_dicts_with_expected_keys(self):
        """Verify that each record is a dict containing the required fields."""
        mgr = make_manager()
        _save_to_db(mgr._conn, sample_info())
        row = mgr.list_files()[0]
        for key in ("id", "filename", "title", "artist", "album", "genre", "year", "comment",
                    "duration", "filesize", "file_created_at", "file_modified_at"):
            self.assertIn(key, row)
        mgr.close()


class TestSearch(unittest.TestCase):

    def setUp(self):
        """Populate the DB with two tracks for search tests."""
        self.mgr = make_manager()
        info_a = {
            "path": "/music/Artist A - Song One.mp3",
            "filename": "Artist A - Song One.mp3",
            "title": "Song One",
            "artist": "Artist A",
            "album": "Album X",
            "genre": "Rock",
            "year": "2020",
            "comment": "great track",
            "duration": 200.0,
            "filesize": 1024,
            "file_created_at": "2024-01-01 00:00:00",
            "file_modified_at": "2024-01-01 00:00:00",
        }
        info_b = {
            "path": "/music/Artist B - Another Track.mp3",
            "filename": "Artist B - Another Track.mp3",
            "title": "Another Track",
            "artist": "Artist B",
            "album": "Album Y",
            "genre": "Jazz",
            "year": "2021",
            "comment": None,
            "duration": 180.0,
            "filesize": 2048,
            "file_created_at": "2024-02-01 00:00:00",
            "file_modified_at": "2024-02-01 00:00:00",
        }
        _save_to_db(self.mgr._conn, info_a)
        _save_to_db(self.mgr._conn, info_b)

    def tearDown(self):
        self.mgr.close()

    def test_search_by_artist(self):
        """Verify that search returns records matching the artist field."""
        results = self.mgr.search("Artist A")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["artist"], "Artist A")

    def test_search_by_title(self):
        """Verify that search returns records matching the title field."""
        results = self.mgr.search("Another Track")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Another Track")

    def test_search_by_album(self):
        """Verify that search returns records matching the album field."""
        results = self.mgr.search("Album X")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["album"], "Album X")

    def test_search_by_filename(self):
        """Verify that search returns records matching the filename field."""
        results = self.mgr.search("Song One")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["filename"], "Artist A - Song One.mp3")

    def test_search_partial_match(self):
        """Verify that partial keywords match multiple records."""
        results = self.mgr.search("Artist")
        self.assertEqual(len(results), 2)

    def test_search_no_match(self):
        """Verify that a non-matching keyword returns an empty list."""
        results = self.mgr.search("XYZ_NOMATCH")
        self.assertEqual(results, [])

    def test_search_case_insensitive(self):
        """Verify that search is case-insensitive."""
        results = self.mgr.search("artist a")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["artist"], "Artist A")

    def test_search_by_genre(self):
        """Verify that search matches the genre field."""
        results = self.mgr.search("Rock")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["genre"], "Rock")

    def test_search_by_year(self):
        """Verify that search matches the year field."""
        results = self.mgr.search("2021")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["year"], "2021")

    def test_search_by_comment(self):
        """Verify that search matches the comment field."""
        results = self.mgr.search("great track")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["comment"], "great track")

    def test_filename_only_excludes_tag_fields(self):
        """Verify that filename_only=True does not match keywords found only in tags."""
        # "Rock" is in the genre tag of info_a but not in any filename
        results = self.mgr.search("Rock", filename_only=True)
        self.assertEqual(results, [])

    def test_filename_only_matches_filename(self):
        """Verify that filename_only=True still matches the filename column."""
        results = self.mgr.search("Song One", filename_only=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["filename"], "Artist A - Song One.mp3")


class TestDelete(unittest.TestCase):

    def test_delete_removes_record(self):
        """Verify that delete() removes the matching record from the database."""
        mgr = make_manager()
        info = sample_info("/music/track.mp3")
        _save_to_db(mgr._conn, info)
        mgr.delete("/music/track.mp3")
        self.assertEqual(mgr.list_files(), [])
        mgr.close()

    def test_delete_nonexistent_path_is_safe(self):
        """Verify that deleting a path not in the DB does not raise an error."""
        mgr = make_manager()
        mgr.delete("/nonexistent/path.mp3")  # should not raise
        mgr.close()


class TestScan(unittest.TestCase):

    def test_scan_empty_directory(self):
        """Verify that scanning an empty directory returns (0, 0, 0)."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(mgr.scan(tmpdir, force=True), (0, 0, 0))
        mgr.close()

    def test_scan_ignores_non_audio_files(self):
        """Verify that non-audio files (txt, jpg, etc.) are not counted or saved."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "notes.txt"), "w").close()
            open(os.path.join(tmpdir, "cover.jpg"), "w").close()
            self.assertEqual(mgr.scan(tmpdir, force=True), (0, 0, 0))
        mgr.close()

    def test_scan_counts_all_supported_formats(self):
        """Verify that all supported audio formats are counted by scan."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            for ext in (".mp3", ".flac", ".ogg", ".wav", ".m4a"):
                open(os.path.join(tmpdir, f"track{ext}"), "w").close()
            processed, skipped, removed = mgr.scan(tmpdir, force=True)
        self.assertEqual(processed, 5)
        mgr.close()

    def test_scan_counts_audio_files(self):
        """Verify that scan returns the correct count of audio files."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "track1.mp3"), "w").close()
            open(os.path.join(tmpdir, "track2.mp3"), "w").close()
            processed, skipped, removed = mgr.scan(tmpdir, force=True)
        self.assertEqual(processed, 2)
        self.assertEqual(skipped, 0)
        mgr.close()

    def test_scan_saves_to_db(self):
        """Verify that scanned MP3 files are persisted in the database."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "song.mp3"), "w").close()
            mgr.scan(tmpdir, force=True)
        self.assertEqual(len(mgr.list_files()), 1)
        mgr.close()

    def test_scan_returns_processed_and_skipped(self):
        """Verify that scan() returns a (processed, skipped, removed) tuple."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.mp3"), "w").close()
            open(os.path.join(tmpdir, "b.mp3"), "w").close()
            processed, skipped, removed = mgr.scan(tmpdir, force=True)
        self.assertEqual(processed, 2)
        self.assertEqual(skipped, 0)
        self.assertEqual(removed, 0)
        mgr.close()

    def test_incremental_scan_skips_unchanged_files(self):
        """Verify that a second scan skips files with unchanged modification time."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.mp3"), "w").close()
            mgr.scan(tmpdir, force=True)                       # first: process all
            processed, skipped, removed = mgr.scan(tmpdir)    # second: skip unchanged
        self.assertEqual(processed, 0)
        self.assertEqual(skipped, 1)
        mgr.close()

    def test_force_scan_removes_stale_records(self):
        """Verify that force scan deletes DB records for files that no longer exist."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = os.path.join(tmpdir, "a.mp3")
            path_b = os.path.join(tmpdir, "b.mp3")
            open(path_a, "w").close()
            open(path_b, "w").close()
            mgr.scan(tmpdir, force=True)
            self.assertEqual(len(mgr.list_files()), 2)
            # Remove one file and force-rescan
            os.unlink(path_b)
            processed, skipped, removed = mgr.scan(tmpdir, force=True)
        self.assertEqual(removed, 1)
        self.assertEqual(len(mgr.list_files()), 1)
        self.assertEqual(mgr.list_files()[0]["path"], path_a)
        mgr.close()

    def test_incremental_scan_does_not_remove_stale_records(self):
        """Verify that incremental scan (force=False) does not delete stale records."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = os.path.join(tmpdir, "a.mp3")
            path_b = os.path.join(tmpdir, "b.mp3")
            open(path_a, "w").close()
            open(path_b, "w").close()
            mgr.scan(tmpdir, force=True)
            # Remove one file and do an incremental scan
            os.unlink(path_b)
            processed, skipped, removed = mgr.scan(tmpdir, force=False)
        self.assertEqual(removed, 0)
        self.assertEqual(len(mgr.list_files()), 2)
        mgr.close()

    def test_scan_progress_callback_called(self):
        """Verify that the progress_callback is invoked once per MP3 file."""
        mgr = make_manager()
        calls = []
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.mp3"), "w").close()
            open(os.path.join(tmpdir, "b.mp3"), "w").close()
            mgr.scan(tmpdir, progress_callback=lambda cur, tot, p: calls.append((cur, tot)), force=True)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1][0], 2)   # last current == total
        self.assertEqual(calls[-1][1], 2)
        mgr.close()

    def test_scan_progress_callback_receives_correct_total(self):
        """Verify that the total passed to progress_callback matches file count."""
        mgr = make_manager()
        totals = []
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                open(os.path.join(tmpdir, f"track{i}.mp3"), "w").close()
            mgr.scan(tmpdir, progress_callback=lambda cur, tot, p: totals.append(tot), force=True)
        self.assertTrue(all(t == 3 for t in totals))
        mgr.close()

    def test_scan_stores_file_timestamps(self):
        """Verify that scan saves file_created_at and file_modified_at."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "song.mp3"), "w").close()
            mgr.scan(tmpdir, force=True)
        row = mgr.list_files()[0]
        self.assertIsNotNone(row["file_created_at"])
        self.assertIsNotNone(row["file_modified_at"])
        # Verify ISO-8601 format: YYYY-MM-DD HH:MM:SS
        import re
        pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
        self.assertRegex(row["file_created_at"], pattern)
        self.assertRegex(row["file_modified_at"], pattern)
        mgr.close()


class TestParseFilenameFallback(unittest.TestCase):

    def _make_info(self, filename: str, artist=None, title=None) -> dict:
        """Return a minimal info dict for testing the fallback parser."""
        return {"filename": filename, "artist": artist, "title": title}

    def test_parses_artist_and_title_from_filename(self):
        """Verify that 'Artist - Title.mp3' yields correct artist and title."""
        info = self._make_info("Artist A - My Song.mp3")
        _parse_filename_fallback(info)
        self.assertEqual(info["artist"], "Artist A")
        self.assertEqual(info["title"], "My Song")

    def test_does_not_overwrite_existing_artist(self):
        """Verify that an existing artist tag is not replaced by filename parsing."""
        info = self._make_info("Artist A - My Song.mp3", artist="Tagged Artist")
        _parse_filename_fallback(info)
        self.assertEqual(info["artist"], "Tagged Artist")
        self.assertEqual(info["title"], "My Song")

    def test_does_not_overwrite_existing_title(self):
        """Verify that an existing title tag is not replaced by filename parsing."""
        info = self._make_info("Artist A - My Song.mp3", title="Tagged Title")
        _parse_filename_fallback(info)
        self.assertEqual(info["artist"], "Artist A")
        self.assertEqual(info["title"], "Tagged Title")

    def test_no_separator_sets_title_to_stem(self):
        """Verify that a filename without ' - ' uses the full stem as title."""
        info = self._make_info("justasong.mp3")
        _parse_filename_fallback(info)
        self.assertIsNone(info["artist"])
        self.assertEqual(info["title"], "justasong")

    def test_multiple_dashes_splits_on_first(self):
        """Verify that only the first ' - ' is used as separator."""
        info = self._make_info("Artist - Title - Live.mp3")
        _parse_filename_fallback(info)
        self.assertEqual(info["artist"], "Artist")
        self.assertEqual(info["title"], "Title - Live")

    def test_scan_parses_filename_when_no_tags(self):
        """Verify that scan uses filename fallback for untagged MP3 files."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "Singer X - Great Song.mp3"), "w").close()
            mgr.scan(tmpdir, force=True)
        row = mgr.list_files()[0]
        self.assertEqual(row["artist"], "Singer X")
        self.assertEqual(row["title"], "Great Song")
        mgr.close()


class TestGetByPath(unittest.TestCase):

    def test_returns_dict_for_existing_path(self):
        """Verify that get_by_path returns a dict when the path exists in the DB."""
        mgr = make_manager()
        _save_to_db(mgr._conn, sample_info("/music/track.mp3"))
        result = mgr.get_by_path("/music/track.mp3")
        self.assertIsNotNone(result)
        self.assertEqual(result["path"], "/music/track.mp3")
        self.assertEqual(result["title"], "Test Song")
        mgr.close()

    def test_returns_none_for_missing_path(self):
        """Verify that get_by_path returns None when the path is not in the DB."""
        mgr = make_manager()
        result = mgr.get_by_path("/music/nonexistent.mp3")
        self.assertIsNone(result)
        mgr.close()

    def test_does_not_return_other_records(self):
        """Verify that get_by_path returns only the record matching the given path."""
        mgr = make_manager()
        _save_to_db(mgr._conn, sample_info("/music/a.mp3"))
        _save_to_db(mgr._conn, sample_info("/music/b.mp3"))
        result = mgr.get_by_path("/music/a.mp3")
        self.assertIsNotNone(result)
        self.assertEqual(result["path"], "/music/a.mp3")
        mgr.close()


if __name__ == "__main__":
    unittest.main()
