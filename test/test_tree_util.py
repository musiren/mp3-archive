"""
test_tree_util.py - Tests for the GUI-independent directory-tree builder.

Runs locally (no Kivy needed); only os.path is used by tree_util.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tree_util import build_tree_rows  # noqa: E402


def _files(*paths):
    """Return record dicts for the given paths."""
    return [{"path": p} for p in paths]


class TestBuildTreeRows(unittest.TestCase):
    """Tests for build_tree_rows()."""

    def test_collapsed_shows_only_top_level(self):
        """Verifies collapsed folders hide their children; top-level files show."""
        files = _files(
            "/m/A/song1.mp3", "/m/A/song2.mp3",
            "/m/B/song3.mp3", "/m/top.mp3",
        )
        rows = build_tree_rows(files, "/m", set())
        texts = [r["text"] for r in rows]
        # Two folder rows (A, B) collapsed + one top-level file row.
        self.assertEqual(sum(r["is_dir"] for r in rows), 2)
        self.assertTrue(any("▶ A" in t for t in texts))
        self.assertTrue(any("▶ B" in t for t in texts))
        self.assertTrue(any("♪ top.mp3" in t for t in texts))
        # Children of collapsed A must not appear.
        self.assertFalse(any("song1.mp3" in t for t in texts))

    def test_expanded_folder_shows_children_indented(self):
        """Verifies an expanded folder reveals its files, indented one level."""
        files = _files("/m/A/song1.mp3", "/m/A/song2.mp3", "/m/B/song3.mp3")
        rows = build_tree_rows(files, "/m", {"A"})
        by_text = {r["text"]: r for r in rows}
        self.assertTrue(any("▼ A" in t for t in by_text))      # A expanded
        self.assertTrue(any("song1.mp3" in t and t.startswith("    ") for t in by_text))
        # B stays collapsed → song3 hidden.
        self.assertFalse(any("song3.mp3" in t for t in by_text))

    def test_file_rows_carry_path_folders_carry_key(self):
        """Verifies file rows expose the path and folder rows expose the key."""
        files = _files("/m/A/song1.mp3")
        rows = build_tree_rows(files, "/m", {"A"})
        folder = next(r for r in rows if r["is_dir"])
        leaf = next(r for r in rows if not r["is_dir"])
        self.assertEqual(folder["key"], "A")
        self.assertEqual(folder["path"], "")
        self.assertEqual(leaf["path"], "/m/A/song1.mp3")
        self.assertEqual(leaf["key"], "")

    def test_nested_folders_use_slash_keys(self):
        """Verifies nested folder keys are slash-joined and expand independently."""
        files = _files("/m/A/B/deep.mp3")
        rows = build_tree_rows(files, "/m", {"A", "A/B"})
        keys = [r["key"] for r in rows if r["is_dir"]]
        self.assertIn("A", keys)
        self.assertIn("A/B", keys)
        self.assertTrue(any("deep.mp3" in r["text"] for r in rows))


if __name__ == "__main__":
    unittest.main()
