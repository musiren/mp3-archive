"""
test_tree_util.py - Tests for the GUI-independent directory-tree builder.

Runs locally (no Kivy needed); only os.path is used by tree_util.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from tree_util import (  # noqa: E402
    TreeIndex,
    build_tree_rows,
    files_under_folder,
    refresh_selection_flags,
)


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

    def test_backslash_paths_build_folders(self):
        """Verifies Windows-style paths group under folders on any host OS."""
        files = [{"path": r"C:\m\A\1.mp3"}]
        rows = build_tree_rows(files, r"C:\m", {"A"})
        folder = next(r for r in rows if r["is_dir"])
        leaf = next(r for r in rows if not r["is_dir"])
        self.assertEqual(folder["key"], "A")
        self.assertEqual(leaf["path"], r"C:\m\A\1.mp3")

    def test_rows_carry_level(self):
        """Verifies rows expose their indentation depth for in-place updates."""
        files = _files("/m/A/B/deep.mp3", "/m/top.mp3")
        rows = build_tree_rows(files, "/m", {"A", "A/B"})
        by_text = {r["text"].strip(): r["level"] for r in rows}
        self.assertEqual(by_text["▼ A"], 0)
        self.assertEqual(by_text["▼ B"], 1)
        self.assertEqual(by_text["♪ deep.mp3"], 2)
        self.assertEqual(by_text["♪ top.mp3"], 0)


class TestTreeIndex(unittest.TestCase):
    """Tests for the cached TreeIndex used by the 트리 view's hot paths."""

    def test_rows_match_build_tree_rows(self):
        """Verifies a reused index renders the same rows as the wrapper."""
        files = _files("/m/A/1.mp3", "/m/A/sub/2.mp3", "/m/B/3.mp3",
                       "/m/top.mp3")
        index = TreeIndex(files, "/m")
        for expanded in (set(), {"A"}, {"A", "A/sub", "B"}):
            self.assertEqual(index.rows(expanded),
                             build_tree_rows(files, "/m", expanded))

    def test_collapsed_children_not_materialised(self):
        """Verifies collapsed folders contribute no child rows (lazy render)."""
        files = _files(*[f"/m/A/{i}.mp3" for i in range(100)], "/m/top.mp3")
        rows = TreeIndex(files, "/m").rows(set())
        self.assertEqual(len(rows), 2)   # the A folder row + top.mp3

    def test_paths_under_matches_files_under_folder(self):
        """Verifies the precomputed folder contents agree with the O(N) scan."""
        files = _files("/m/A/1.mp3", "/m/A/sub/2.mp3", "/m/B/3.mp3")
        index = TreeIndex(files, "/m")
        for key in ("A", "A/sub", "B"):
            expected = {f["path"]
                        for f in files_under_folder(files, "/m", key)}
            self.assertEqual(set(index.paths_under(key)), expected)

    def test_paths_under_unknown_or_empty_key(self):
        """Verifies an unknown or empty key yields no paths."""
        index = TreeIndex(_files("/m/A/1.mp3"), "/m")
        self.assertEqual(index.paths_under("nope"), [])
        self.assertEqual(index.paths_under(""), [])

    def test_selected_flags(self):
        """Verifies file flags and the all-files-selected folder flag."""
        files = _files("/m/A/1.mp3", "/m/A/2.mp3")
        index = TreeIndex(files, "/m")
        rows = index.rows({"A"}, selected={"/m/A/1.mp3"})
        flags = {r["text"].strip(): r["selected"] for r in rows}
        self.assertFalse(flags["▼ A"])       # only one of two selected
        self.assertTrue(flags["♪ 1.mp3"])
        self.assertFalse(flags["♪ 2.mp3"])
        rows = index.rows({"A"}, selected={"/m/A/1.mp3", "/m/A/2.mp3"})
        self.assertTrue(next(r for r in rows if r["is_dir"])["selected"])

    def test_render_is_fast_once_indexed(self):
        """Verifies repeated renders on a big tree avoid re-indexing costs."""
        import time
        files = _files(*[f"/m/d{i // 100}/{i}.mp3" for i in range(20_000)])
        index = TreeIndex(files, "/m")
        start = time.perf_counter()
        for i in range(50):                 # 50 expand/collapse taps
            index.rows({f"d{i}"})
        elapsed = time.perf_counter() - start
        # The old per-tap rebuild took O(N) + O(N) per visible folder row
        # (~200 folders x 20k files); the indexed render walks only visible
        # rows. 2s leaves generous headroom for slow machines.
        self.assertLess(elapsed, 2.0)


class TestRefreshSelectionFlags(unittest.TestCase):
    """Tests for the in-place selection-flag updater."""

    def _setup(self):
        """Return (index, expanded rows) for a two-folder tree."""
        files = _files("/m/A/1.mp3", "/m/A/2.mp3", "/m/A/sub/3.mp3",
                       "/m/B/4.mp3")
        index = TreeIndex(files, "/m")
        rows = index.rows({"A", "A/sub", "B"})
        return index, rows

    def _row_at(self, rows, label):
        """Return the index of the row whose stripped text equals *label*."""
        return next(i for i, r in enumerate(rows)
                    if r["text"].strip() == label)

    def test_file_toggle_updates_row_and_ancestors(self):
        """Verifies selecting the last file flips it and its folder chain."""
        index, rows = self._setup()
        selected = {"/m/A/1.mp3", "/m/A/2.mp3", "/m/A/sub/3.mp3"}
        start = self._row_at(rows, "♪ 3.mp3")
        refresh_selection_flags(rows, start, selected, index.paths_under)
        self.assertTrue(rows[start]["selected"])
        self.assertTrue(rows[self._row_at(rows, "▼ sub")]["selected"])
        self.assertTrue(rows[self._row_at(rows, "▼ A")]["selected"])
        self.assertFalse(rows[self._row_at(rows, "▼ B")]["selected"])

    def test_folder_toggle_updates_descendants(self):
        """Verifies selecting a folder flips its visible descendant rows."""
        index, rows = self._setup()
        selected = set(index.paths_under("A"))
        start = self._row_at(rows, "▼ A")
        refresh_selection_flags(rows, start, selected, index.paths_under)
        for label in ("▼ A", "♪ 1.mp3", "♪ 2.mp3", "▼ sub", "♪ 3.mp3"):
            self.assertTrue(rows[self._row_at(rows, label)]["selected"], label)
        self.assertFalse(rows[self._row_at(rows, "▼ B")]["selected"])

    def test_deselect_propagates_up(self):
        """Verifies deselecting one file clears its ancestors' flags."""
        index, rows = self._setup()
        all_a = set(index.paths_under("A"))
        start = self._row_at(rows, "▼ A")
        refresh_selection_flags(rows, start, all_a, index.paths_under)
        all_a.discard("/m/A/sub/3.mp3")     # then deselect the nested file
        start = self._row_at(rows, "♪ 3.mp3")
        refresh_selection_flags(rows, start, all_a, index.paths_under)
        self.assertFalse(rows[self._row_at(rows, "♪ 3.mp3")]["selected"])
        self.assertFalse(rows[self._row_at(rows, "▼ sub")]["selected"])
        self.assertFalse(rows[self._row_at(rows, "▼ A")]["selected"])
        self.assertTrue(rows[self._row_at(rows, "♪ 1.mp3")]["selected"])

    def test_does_not_touch_unrelated_rows(self):
        """Verifies rows outside the affected groups keep their stale flags."""
        index, rows = self._setup()
        b_file = self._row_at(rows, "♪ 4.mp3")
        rows[b_file]["selected"] = True     # deliberately stale
        start = self._row_at(rows, "♪ 1.mp3")
        refresh_selection_flags(rows, start, {"/m/A/1.mp3"},
                                index.paths_under)
        self.assertTrue(rows[b_file]["selected"])   # untouched by design

    def test_out_of_range_start_is_noop(self):
        """Verifies an out-of-range start index changes nothing."""
        index, rows = self._setup()
        before = [dict(r) for r in rows]
        refresh_selection_flags(rows, 99, {"/m/A/1.mp3"}, index.paths_under)
        refresh_selection_flags(rows, -1, {"/m/A/1.mp3"}, index.paths_under)
        self.assertEqual(rows, before)


if __name__ == "__main__":
    unittest.main()
