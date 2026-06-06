"""
test_audio_meta.py - Tests for the GUI-independent audio_meta helpers.

These run locally (no PyQt6 or Kivy needed); only mutagen is required.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from audio_meta import get_album_art, get_lyrics, to_easy_tags  # noqa: E402


class TestGetLyrics(unittest.TestCase):
    """Tests for get_lyrics()."""

    def test_returns_none_for_empty_path(self):
        """Verifies get_lyrics returns None for an empty path."""
        self.assertIsNone(get_lyrics(""))

    def test_returns_none_for_nonexistent_file(self):
        """Verifies get_lyrics returns None for a path that does not exist."""
        self.assertIsNone(get_lyrics("/no/such/file.mp3"))

    def test_returns_none_for_non_audio_file(self):
        """Verifies get_lyrics returns None for a plain text file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not audio")
            path = f.name
        try:
            self.assertIsNone(get_lyrics(path))
        finally:
            os.remove(path)


class TestGetAlbumArt(unittest.TestCase):
    """Tests for get_album_art()."""

    def test_returns_none_for_nonexistent_file(self):
        """Verifies get_album_art returns None for a missing file."""
        self.assertIsNone(get_album_art("/no/such/file.mp3"))

    def test_returns_none_for_non_audio_file(self):
        """Verifies get_album_art returns None for a plain text file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not audio")
            path = f.name
        try:
            self.assertIsNone(get_album_art(path))
        finally:
            os.remove(path)


class TestToEasyTags(unittest.TestCase):
    """Tests for to_easy_tags() form-to-tag mapping."""

    def test_maps_year_to_date(self):
        """Verifies the 'year' form field maps to the easy-tag 'date' key."""
        tags = to_easy_tags({"year": "2020"})
        self.assertEqual(tags, {"date": "2020"})

    def test_drops_blank_values(self):
        """Verifies blank/whitespace fields are omitted so they don't clobber tags."""
        tags = to_easy_tags({"title": "Song", "artist": "", "album": "   "})
        self.assertEqual(tags, {"title": "Song"})

    def test_strips_and_maps_known_fields(self):
        """Verifies known fields are stripped and mapped to easy-tag keys."""
        tags = to_easy_tags({
            "title": " T ", "artist": "A", "album": "Al",
            "genre": "Pop", "comment": "c", "unknown": "x",
        })
        self.assertEqual(tags, {
            "title": "T", "artist": "A", "album": "Al",
            "genre": "Pop", "comment": "c",
        })


if __name__ == "__main__":
    unittest.main()
