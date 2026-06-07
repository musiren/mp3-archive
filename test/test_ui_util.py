"""
test_ui_util.py - Tests for the GUI-independent UI-chrome helpers.

Runs locally (no Kivy/PyQt needed); ui_util imports only stdlib.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ui_util import (  # noqa: E402
    latest_news_version,
    resolve_theme_style,
    sort_files,
)


def _f(filename="x.mp3", artist=None, title=None, modified=None):
    """Build a minimal file-info dict for the sort tests."""
    return {
        "filename": filename,
        "artist": artist,
        "title": title,
        "file_modified_at": modified,
    }


class TestSortFiles(unittest.TestCase):
    """Tests for sort_files()."""

    def test_does_not_mutate_input(self):
        """Verify the original list is left unchanged."""
        files = [_f("b.mp3"), _f("a.mp3")]
        sort_files(files, "name")
        self.assertEqual([f["filename"] for f in files], ["b.mp3", "a.mp3"])

    def test_sort_by_name_case_insensitive(self):
        """Verify filename sort is ascending and case-insensitive."""
        files = [_f("banana.mp3"), _f("Apple.mp3"), _f("cherry.mp3")]
        out = sort_files(files, "name")
        self.assertEqual([f["filename"] for f in out],
                         ["Apple.mp3", "banana.mp3", "cherry.mp3"])

    def test_sort_by_artist_then_title(self):
        """Verify artist sort breaks ties on the title."""
        files = [
            _f(artist="Queen", title="Two"),
            _f(artist="ABBA",  title="Z"),
            _f(artist="Queen", title="One"),
        ]
        out = sort_files(files, "artist")
        self.assertEqual([(f["artist"], f["title"]) for f in out],
                         [("ABBA", "Z"), ("Queen", "One"), ("Queen", "Two")])

    def test_sort_by_title(self):
        """Verify title sort orders by the title field."""
        files = [_f(title="Charlie"), _f(title="alpha"), _f(title="Bravo")]
        out = sort_files(files, "title")
        self.assertEqual([f["title"] for f in out], ["alpha", "Bravo", "Charlie"])

    def test_missing_values_sort_last(self):
        """Verify None and the "-" placeholder sort after real values."""
        files = [_f(artist="-"), _f(artist="Beatles"), _f(artist=None)]
        out = sort_files(files, "artist")
        self.assertEqual(out[0]["artist"], "Beatles")
        self.assertIn(out[1]["artist"], ("-", None))
        self.assertIn(out[2]["artist"], ("-", None))

    def test_sort_by_date_newest_first(self):
        """Verify date sort is newest-first using the modified timestamp."""
        files = [
            _f("old.mp3",  modified="2024-01-01 10:00:00"),
            _f("new.mp3",  modified="2026-06-01 10:00:00"),
            _f("mid.mp3",  modified="2025-03-01 10:00:00"),
        ]
        out = sort_files(files, "date")
        self.assertEqual([f["filename"] for f in out],
                         ["new.mp3", "mid.mp3", "old.mp3"])

    def test_date_sort_puts_undated_last(self):
        """Verify files without a modified timestamp sort to the end."""
        files = [_f("none.mp3", modified=None),
                 _f("dated.mp3", modified="2025-01-01 00:00:00")]
        out = sort_files(files, "date")
        self.assertEqual([f["filename"] for f in out], ["dated.mp3", "none.mp3"])

    def test_unknown_mode_keeps_order(self):
        """Verify an unrecognised mode returns the list in its original order."""
        files = [_f("b.mp3"), _f("a.mp3")]
        out = sort_files(files, "whatever")
        self.assertEqual([f["filename"] for f in out], ["b.mp3", "a.mp3"])


class TestResolveThemeStyle(unittest.TestCase):
    """Tests for resolve_theme_style()."""

    def test_explicit_light(self):
        """Verify an explicit light choice maps to 'Light'."""
        self.assertEqual(resolve_theme_style("light", device_is_dark=True), "Light")

    def test_explicit_dark(self):
        """Verify an explicit dark choice maps to 'Dark'."""
        self.assertEqual(resolve_theme_style("dark", device_is_dark=False), "Dark")

    def test_system_follows_device_dark(self):
        """Verify 'system' returns 'Dark' when the device is in night mode."""
        self.assertEqual(resolve_theme_style("system", device_is_dark=True), "Dark")

    def test_system_follows_device_light(self):
        """Verify 'system' returns 'Light' when the device is not in night mode."""
        self.assertEqual(resolve_theme_style("system", device_is_dark=False), "Light")

    def test_unknown_choice_defaults_to_device(self):
        """Verify an unknown choice falls back to following the device."""
        self.assertEqual(resolve_theme_style("", device_is_dark=True), "Dark")
        self.assertEqual(resolve_theme_style("", device_is_dark=False), "Light")


class TestLatestNewsVersion(unittest.TestCase):
    """Tests for latest_news_version()."""

    def test_extracts_first_version_header(self):
        """Verify the newest-first version token is returned."""
        news = (
            "mp3-archive NEWS\n\n"
            "=====\n"
            "v20260420 (2026-04-20)\n"
            "=====\n"
            "- something\n\n"
            "v20260407 (2026-04-07)\n"
        )
        self.assertEqual(latest_news_version(news), "v20260420")

    def test_empty_text_returns_empty(self):
        """Verify empty or None input returns an empty string."""
        self.assertEqual(latest_news_version(""), "")
        self.assertEqual(latest_news_version(None), "")

    def test_no_version_header_returns_empty(self):
        """Verify text without a vNNNNNN header returns an empty string."""
        self.assertEqual(latest_news_version("just some notes\nno version here"), "")


if __name__ == "__main__":
    unittest.main()
