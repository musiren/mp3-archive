"""
test_audio_meta.py - Tests for the GUI-independent audio_meta helpers.

These run locally (no PyQt6 or Kivy needed); only mutagen is required.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from audio_meta import fix_mojibake, get_album_art, get_lyrics, to_easy_tags  # noqa: E402


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


class TestFixMojibake(unittest.TestCase):
    """Tests for CP949/EUC-KR-as-Latin-1 mojibake repair."""

    def test_repairs_cp949_decoded_as_latin1(self):
        """Verifies Korean read as Latin-1 from CP949 bytes is restored."""
        original = "아주오래된연인들"
        mojibake = original.encode("cp949").decode("latin-1")
        self.assertEqual(fix_mojibake(mojibake), original)

    def test_leaves_correct_korean_unchanged(self):
        """Verifies already-correct Korean (Hangul) is returned unchanged."""
        self.assertEqual(fix_mojibake("내맘이야"), "내맘이야")

    def test_leaves_latin_text_unchanged(self):
        """Verifies genuine Latin titles are not falsely 'repaired'."""
        for s in ["Smells Like Teen Spirit", "015B", "TakeTwo", "Vlad"]:
            self.assertEqual(fix_mojibake(s), s)

    def test_handles_none_and_empty(self):
        """Verifies None and empty string pass through untouched."""
        self.assertIsNone(fix_mojibake(None))
        self.assertEqual(fix_mojibake(""), "")


if __name__ == "__main__":
    unittest.main()
