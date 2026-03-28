"""
test_mp3_manager.py - Unit tests for src/mp3_manager.py.

Tests use an in-memory SQLite database and temporary files
to avoid side effects on the real filesystem.
"""

import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mp3_manager import create_table, save_to_db, list_files, scan_directory


def make_conn() -> sqlite3.Connection:
    """Return an in-memory SQLite connection with the schema applied."""
    conn = sqlite3.connect(":memory:")
    create_table(conn)
    return conn


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
    }


class TestCreateTable(unittest.TestCase):

    def test_table_exists_after_create(self):
        """Verify that mp3_files table is created successfully."""
        conn = make_conn()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mp3_files'"
        )
        self.assertIsNotNone(cursor.fetchone())
        conn.close()

    def test_create_table_is_idempotent(self):
        """Verify that calling create_table twice does not raise an error."""
        conn = make_conn()
        create_table(conn)  # second call should be safe
        conn.close()


class TestSaveToDb(unittest.TestCase):

    def test_save_inserts_record(self):
        """Verify that save_to_db inserts a new record into the database."""
        conn = make_conn()
        save_to_db(conn, sample_info())
        cursor = conn.execute("SELECT COUNT(*) FROM mp3_files")
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

    def test_save_replaces_on_duplicate_path(self):
        """Verify that saving the same path twice updates the existing record."""
        conn = make_conn()
        info = sample_info()
        save_to_db(conn, info)
        info["title"] = "Updated Title"
        save_to_db(conn, info)
        cursor = conn.execute("SELECT COUNT(*) FROM mp3_files")
        self.assertEqual(cursor.fetchone()[0], 1)
        cursor = conn.execute("SELECT title FROM mp3_files")
        self.assertEqual(cursor.fetchone()[0], "Updated Title")
        conn.close()

    def test_save_stores_correct_fields(self):
        """Verify that all metadata fields are stored correctly."""
        conn = make_conn()
        info = sample_info()
        save_to_db(conn, info)
        cursor = conn.execute(
            "SELECT filename, title, artist, album, duration, filesize FROM mp3_files"
        )
        row = cursor.fetchone()
        self.assertEqual(row[0], "test.mp3")
        self.assertEqual(row[1], "Test Song")
        self.assertEqual(row[2], "Test Artist")
        self.assertEqual(row[3], "Test Album")
        self.assertAlmostEqual(row[4], 180.0)
        self.assertEqual(row[5], 4096)
        conn.close()


class TestListFiles(unittest.TestCase):

    def test_list_empty_db(self):
        """Verify that list_files returns an empty list for an empty database."""
        conn = make_conn()
        self.assertEqual(list_files(conn), [])
        conn.close()

    def test_list_returns_all_records(self):
        """Verify that list_files returns all inserted records."""
        conn = make_conn()
        save_to_db(conn, sample_info("/music/a.mp3"))
        save_to_db(conn, sample_info("/music/b.mp3"))
        results = list_files(conn)
        self.assertEqual(len(results), 2)
        conn.close()

    def test_list_returns_dicts(self):
        """Verify that list_files returns a list of dictionaries."""
        conn = make_conn()
        save_to_db(conn, sample_info())
        results = list_files(conn)
        self.assertIsInstance(results[0], dict)
        self.assertIn("filename", results[0])
        conn.close()


class TestScanDirectory(unittest.TestCase):

    def test_scan_empty_directory(self):
        """Verify that scanning an empty directory saves nothing."""
        conn = make_conn()
        with tempfile.TemporaryDirectory() as tmpdir:
            count = scan_directory(conn, tmpdir)
        self.assertEqual(count, 0)
        conn.close()

    def test_scan_ignores_non_mp3_files(self):
        """Verify that non-MP3 files are ignored during scan."""
        conn = make_conn()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "readme.txt"), "w").close()
            open(os.path.join(tmpdir, "song.flac"), "w").close()
            count = scan_directory(conn, tmpdir)
        self.assertEqual(count, 0)
        conn.close()

    def test_scan_counts_mp3_files(self):
        """Verify that scan_directory counts and saves MP3 files correctly."""
        conn = make_conn()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create dummy .mp3 files (empty, no real audio data)
            open(os.path.join(tmpdir, "track1.mp3"), "w").close()
            open(os.path.join(tmpdir, "track2.mp3"), "w").close()
            count = scan_directory(conn, tmpdir)
        self.assertEqual(count, 2)
        conn.close()


if __name__ == "__main__":
    unittest.main()
