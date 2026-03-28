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

from mp3_manager import Mp3Manager, _create_table, _save_to_db, _list_files


def make_manager() -> Mp3Manager:
    """Return an Mp3Manager backed by an in-memory SQLite database."""
    mgr = Mp3Manager.__new__(Mp3Manager)
    import sqlite3
    mgr._conn = sqlite3.connect(":memory:")
    _create_table(mgr._conn)
    return mgr


def sample_info(path: str = "/music/test.mp3") -> dict:
    """Return a sample MP3 info dictionary for testing."""
    return {
        "path": path,
        "filename": os.path.basename(path),
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
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
        for key in ("id", "filename", "title", "artist", "album", "duration", "filesize",
                    "file_created_at", "file_modified_at"):
            self.assertIn(key, row)
        mgr.close()


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
        """Verify that scanning an empty directory returns 0."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual(mgr.scan(tmpdir), 0)
        mgr.close()

    def test_scan_ignores_non_mp3_files(self):
        """Verify that non-MP3 files are not counted or saved."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "notes.txt"), "w").close()
            open(os.path.join(tmpdir, "song.flac"), "w").close()
            self.assertEqual(mgr.scan(tmpdir), 0)
        mgr.close()

    def test_scan_counts_mp3_files(self):
        """Verify that scan returns the correct count of MP3 files."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "track1.mp3"), "w").close()
            open(os.path.join(tmpdir, "track2.mp3"), "w").close()
            self.assertEqual(mgr.scan(tmpdir), 2)
        mgr.close()

    def test_scan_saves_to_db(self):
        """Verify that scanned MP3 files are persisted in the database."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "song.mp3"), "w").close()
            mgr.scan(tmpdir)
        self.assertEqual(len(mgr.list_files()), 1)
        mgr.close()

    def test_scan_progress_callback_called(self):
        """Verify that the progress_callback is invoked once per MP3 file."""
        mgr = make_manager()
        calls = []
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.mp3"), "w").close()
            open(os.path.join(tmpdir, "b.mp3"), "w").close()
            mgr.scan(tmpdir, progress_callback=lambda cur, tot, p: calls.append((cur, tot)))
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
            mgr.scan(tmpdir, progress_callback=lambda cur, tot, p: totals.append(tot))
        self.assertTrue(all(t == 3 for t in totals))
        mgr.close()

    def test_scan_stores_file_timestamps(self):
        """Verify that scan saves file_created_at and file_modified_at."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "song.mp3"), "w").close()
            mgr.scan(tmpdir)
        row = mgr.list_files()[0]
        self.assertIsNotNone(row["file_created_at"])
        self.assertIsNotNone(row["file_modified_at"])
        # Verify ISO-8601 format: YYYY-MM-DD HH:MM:SS
        import re
        pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
        self.assertRegex(row["file_created_at"], pattern)
        self.assertRegex(row["file_modified_at"], pattern)
        mgr.close()


if __name__ == "__main__":
    unittest.main()
