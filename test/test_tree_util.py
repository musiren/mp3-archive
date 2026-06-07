"""
test_tree_util.py - Tests for the GUI-independent directory-tree builder.

Runs locally (no Kivy needed); only os.path is used by tree_util.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tree_util import build_tree_rows, files_under_folder  # noqa: E402


def _files(*paths):
    """Return record dicts for the given paths."""
    return [{"path": p} for p in paths]


class TestFilesUnderFolder(unittest.TestCase):
    """Tests for files_under_folder()."""

    def test_collects_direct_and_nested_files(self):
        """Verify files directly in and nested under the folder are returned."""
        base = "/m"
        files = _files("/m/a/1.mp3", "/m/a/sub/2.mp3", "/m/b/3.mp3")
        out = files_under_folder(files, base, "a")
        self.assertEqual([f["path"] for f in out],
                         ["/m/a/1.mp3", "/m/a/sub/2.mp3"])

    def test_excludes_sibling_with_shared_prefix(self):
        """Verify a sibling folder sharing a name prefix is not matched."""
        base = "/m"
        files = _files("/m/260419/x.mp3", "/m/2604190/y.mp3")
        out = files_under_folder(files, base, "260419")
        self.assertEqual([f["path"] for f in out], ["/m/260419/x.mp3"])

    def test_nested_folder_key(self):
        """Verify a nested folder key matches only its own subtree."""
        base = "/m"
        files = _files("/m/a/live/1.mp3", "/m/a/2.mp3")
        out = files_under_folder(files, base, "a/live")
        self.assertEqual([f["path"] for f in out], ["/m/a/live/1.mp3"])

    def test_ordered_by_relative_path(self):
        """Verify results are ordered by case-folded relative path."""
        base = "/m"
        files = _files("/m/a/Zebra.mp3", "/m/a/apple.mp3", "/m/a/sub/0.mp3")
        out = files_under_folder(files, base, "a")
        # case-folded rel order: a/apple.mp3 < a/sub/0.mp3 < a/zebra.mp3
        self.assertEqual([os.path.basename(f["path"]) for f in out],
                         ["apple.mp3", "0.mp3", "Zebra.mp3"])

    def test_backslash_paths_match(self):
        """Verify Windows-style backslash paths are normalised and matched."""
        base = r"C:\m"
        files = [{"path": r"C:\m\a\1.mp3"}, {"path": r"C:\m\b\2.mp3"}]
        out = files_under_folder(files, base, "a")
        self.assertEqual([f["path"] for f in out], [r"C:\m\a\1.mp3"])

    def test_empty_base_full_paths_match(self):
        """Verify empty base (no scan dir, e.g. after relaunch) still matches.

        With base="" the tree is keyed off full paths; build_tree_rows drops
        the leading "/" when forming keys, so files_under_folder must too.
        """
        files = _files("/storage/0/Music/260419/x.mp3",
                       "/storage/0/Music/260420/y.mp3")
        out = files_under_folder(files, "", "storage/0/Music/260419")
        self.assertEqual([f["path"] for f in out],
                         ["/storage/0/Music/260419/x.mp3"])

    def test_empty_base_key_matches_build_tree_rows(self):
        """Verify the folder key emitted by build_tree_rows resolves under empty base."""
        files = _files("/storage/0/Music/260419/x.mp3",
                       "/storage/0/Music/260419/sub/z.mp3")
        rows = build_tree_rows(files, "", set())
        folder_key = next(r["key"] for r in rows if r["is_dir"])
        out = files_under_folder(files, "", folder_key)
        self.assertEqual(len(out), 2)

    def test_empty_key_returns_empty(self):
        """Verify an empty folder key returns no files."""
        self.assertEqual(files_under_folder(_files("/m/a/1.mp3"), "/m", ""), [])

    def test_no_match_returns_empty(self):
        """Verify a folder with no files under it returns an empty list."""
        self.assertEqual(files_under_folder(_files("/m/a/1.mp3"), "/m", "b"), [])

    def test_preserves_record_objects(self):
        """Verify the returned items are the original record dicts (with all keys)."""
        base = "/m"
        rec = {"path": "/m/a/1.mp3", "title": "One", "artist": "X"}
        out = files_under_folder([rec], base, "a")
        self.assertEqual(out[0]["title"], "One")
        self.assertEqual(out[0]["artist"], "X")


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
