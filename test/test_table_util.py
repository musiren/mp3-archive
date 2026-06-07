"""
test_table_util.py - Tests for the GUI-independent 표 (table) view helpers.

Runs locally (no Kivy needed); table_util imports only stdlib.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from table_util import (  # noqa: E402
    DEFAULT_COLUMNS,
    available_columns,
    column_label,
    column_width,
    format_cell,
    header_label,
    is_numeric_column,
    next_sort,
    row_values,
    sort_files_by,
    toggle_column,
)


class TestColumnModel(unittest.TestCase):
    """Tests for the column definitions and lookups."""

    def test_available_columns_have_four_tuple_shape(self):
        """Verify each column def is (key, label, width, numeric)."""
        for col in available_columns():
            self.assertEqual(len(col), 4)

    def test_default_columns_are_known(self):
        """Verify every default column key exists in the definitions."""
        keys = {k for k, *_ in available_columns()}
        for key in DEFAULT_COLUMNS:
            self.assertIn(key, keys)

    def test_label_width_numeric_lookups(self):
        """Verify label/width/numeric lookups for a known column."""
        self.assertEqual(column_label("title"), "제목")
        self.assertGreater(column_width("title"), 0)
        self.assertTrue(is_numeric_column("duration"))
        self.assertFalse(is_numeric_column("title"))

    def test_unknown_key_lookups_are_safe(self):
        """Verify lookups fall back gracefully for an unknown key."""
        self.assertEqual(column_label("nope"), "nope")
        self.assertEqual(column_width("nope"), 120)
        self.assertFalse(is_numeric_column("nope"))


class TestFormatCell(unittest.TestCase):
    """Tests for format_cell()."""

    def test_duration_formatted_as_minutes_seconds(self):
        """Verify duration is rendered as M:SS."""
        self.assertEqual(format_cell("duration", 95), "1:35")

    def test_duration_blank_when_missing(self):
        """Verify a missing/zero duration renders as empty."""
        self.assertEqual(format_cell("duration", None), "")
        self.assertEqual(format_cell("duration", 0), "")

    def test_filesize_formatted(self):
        """Verify filesize renders as KB/MB."""
        self.assertEqual(format_cell("filesize", 1536), "1.5 KB")
        self.assertEqual(format_cell("filesize", 5 * 1024 * 1024), "5.0 MB")

    def test_text_value_stringified_and_none_blank(self):
        """Verify plain text values pass through and None becomes ''."""
        self.assertEqual(format_cell("title", "Song"), "Song")
        self.assertEqual(format_cell("title", None), "")

    def test_row_values_orders_by_column_keys(self):
        """Verify row_values returns formatted cells in the requested order."""
        info = {"title": "T", "artist": "A", "duration": 60}
        self.assertEqual(
            row_values(info, ["artist", "title", "duration"]),
            ["A", "T", "1:00"],
        )


class TestSortFilesBy(unittest.TestCase):
    """Tests for sort_files_by()."""

    def _files(self):
        """Return rows with text, numeric, and missing values to sort."""
        return [
            {"title": "banana", "duration": 200},
            {"title": "apple",  "duration": None},   # missing duration
            {"title": "cherry", "duration": 100},
            {"title": "",       "duration": 150},     # missing title
        ]

    def test_text_ascending_missing_last(self):
        """Verify text sort is ascending with missing titles last."""
        out = sort_files_by(self._files(), "title")
        self.assertEqual([f["title"] for f in out[:3]],
                         ["apple", "banana", "cherry"])
        self.assertEqual(out[3]["title"], "")

    def test_text_descending_keeps_missing_last(self):
        """Verify descending text sort still keeps missing titles last."""
        out = sort_files_by(self._files(), "title", reverse=True)
        self.assertEqual([f["title"] for f in out[:3]],
                         ["cherry", "banana", "apple"])
        self.assertEqual(out[3]["title"], "")

    def test_numeric_ascending_missing_last(self):
        """Verify numeric sort orders by value with missing values last."""
        out = sort_files_by(self._files(), "duration")
        durations = [f["duration"] for f in out]
        self.assertEqual(durations[:3], [100, 150, 200])
        self.assertIsNone(durations[3])

    def test_numeric_descending_missing_last(self):
        """Verify descending numeric sort keeps missing values last."""
        out = sort_files_by(self._files(), "duration", reverse=True)
        durations = [f["duration"] for f in out]
        self.assertEqual(durations[:3], [200, 150, 100])
        self.assertIsNone(durations[3])

    def test_does_not_mutate_input(self):
        """Verify the original list order is preserved."""
        files = self._files()
        sort_files_by(files, "title")
        self.assertEqual(files[0]["title"], "banana")


class TestNextSort(unittest.TestCase):
    """Tests for the header-tap sort state machine."""

    def test_new_column_sorts_ascending(self):
        """Verify tapping a different column resets to ascending."""
        self.assertEqual(next_sort("title", True, "artist"), ("artist", False))

    def test_same_column_toggles_direction(self):
        """Verify tapping the active column flips the direction."""
        self.assertEqual(next_sort("title", False, "title"), ("title", True))
        self.assertEqual(next_sort("title", True, "title"), ("title", False))

    def test_from_no_sort(self):
        """Verify tapping any column from no-sort sorts it ascending."""
        self.assertEqual(next_sort(None, False, "year"), ("year", False))


class TestToggleColumn(unittest.TestCase):
    """Tests for toggle_column()."""

    def test_remove_present_column(self):
        """Verify toggling a present column removes it."""
        out = toggle_column(["title", "artist"], "artist")
        self.assertEqual(out, ["title"])

    def test_add_absent_column_in_definition_order(self):
        """Verify adding a column re-orders the result to definition order."""
        # artist comes before album, which comes before year in the defs.
        out = toggle_column(["year", "album"], "artist")
        self.assertEqual(out, ["artist", "album", "year"])

    def test_toggle_is_idempotent_pair(self):
        """Verify adding then removing returns to the original set."""
        once = toggle_column(["title"], "album")
        twice = toggle_column(once, "album")
        self.assertEqual(twice, ["title"])


class TestHeaderLabel(unittest.TestCase):
    """Tests for header_label()."""

    def test_unsorted_column_is_plain_label(self):
        """Verify a non-active column shows just its label."""
        self.assertEqual(header_label("title", "artist", False), "제목")

    def test_active_ascending_shows_up_arrow(self):
        """Verify the active ascending column shows a ▲."""
        self.assertEqual(header_label("title", "title", False), "제목 ▲")

    def test_active_descending_shows_down_arrow(self):
        """Verify the active descending column shows a ▼."""
        self.assertEqual(header_label("title", "title", True), "제목 ▼")


if __name__ == "__main__":
    unittest.main()
