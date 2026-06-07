"""
test_online_meta.py - Tests for the GUI-independent online-metadata helpers.

Runs locally (no Kivy/PyQt needed); online_meta imports only stdlib.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from online_meta import build_song_query, clean_query_field  # noqa: E402


class TestCleanQueryField(unittest.TestCase):
    """Tests for clean_query_field()."""

    def test_none_returns_none(self):
        """Verify None passes through as None."""
        self.assertIsNone(clean_query_field(None))

    def test_empty_returns_none(self):
        """Verify an empty string returns None."""
        self.assertIsNone(clean_query_field(""))

    def test_whitespace_returns_none(self):
        """Verify a whitespace-only string returns None."""
        self.assertIsNone(clean_query_field("   "))

    def test_dash_placeholder_returns_none(self):
        """Verify the '-' missing-tag placeholder returns None."""
        self.assertIsNone(clean_query_field("-"))

    def test_value_is_trimmed(self):
        """Verify a real value is trimmed of surrounding whitespace."""
        self.assertEqual(clean_query_field("  Queen  "), "Queen")


class TestBuildSongQuery(unittest.TestCase):
    """Tests for build_song_query()."""

    def test_both_fields_present(self):
        """Verify both artist and title are returned when present."""
        self.assertEqual(
            build_song_query({"artist": "Queen", "title": "Bohemian Rhapsody"}),
            ("Queen", "Bohemian Rhapsody"),
        )

    def test_placeholder_artist_becomes_none(self):
        """Verify a '-' artist placeholder is dropped while title is kept."""
        self.assertEqual(
            build_song_query({"artist": "-", "title": "Song"}),
            (None, "Song"),
        )

    def test_missing_keys_become_none(self):
        """Verify absent artist/title keys yield (None, None)."""
        self.assertEqual(build_song_query({}), (None, None))


if __name__ == "__main__":
    unittest.main()
