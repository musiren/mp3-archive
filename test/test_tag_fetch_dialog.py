"""
test_tag_fetch_dialog.py - Unit tests for src/tag_fetch_dialog.py.

All network calls and QThread execution are replaced with unittest.mock
so tests run offline and synchronously.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication

# Shared QApplication instance required by all Qt widget tests.
_app = QApplication.instance() or QApplication(sys.argv)

from tag_fetch_dialog import (
    TagFetchDialog,
    _FetchWorker,
    _SRC_MB,
    _SRC_ITUNES,
    _SRC_BOTH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file(filename="track.mp3", title=None, artist=None, path="/tmp/track.mp3"):
    """Return a minimal file dict as returned by Mp3Manager.list_files()."""
    return {
        "filename": filename,
        "title":    title,
        "artist":   artist,
        "album":    None,
        "path":     path,
    }


def _make_dialog(files, worker_autostart=False):
    """
    Return a TagFetchDialog with the worker thread blocked from starting.

    Blocking _load_current prevents background threads from spinning up
    during tests that only need to inspect the initial state.
    """
    manager = MagicMock()
    with patch.object(TagFetchDialog, "_load_current"):
        dlg = TagFetchDialog(manager, files)
    dlg._manager = manager
    return dlg


# ---------------------------------------------------------------------------
# _FetchWorker
# ---------------------------------------------------------------------------

class TestFetchWorker(unittest.TestCase):

    def test_worker_musicbrainz_only(self):
        """source=musicbrainz calls tag_fetcher.search and tags results."""
        mb_result = [{"title": "Song", "artist": "A", "album": "", "year": "2020", "score": 90}]
        with patch("tag_fetcher.search", return_value=mb_result) as mb_mock, \
             patch("itunes_fetcher.search", return_value=[]) as it_mock:
            worker = _FetchWorker("A", "Song", _SRC_MB)
            emitted = []
            worker.finished.connect(emitted.append)
            worker.run()

        mb_mock.assert_called_once_with("A", "Song")
        it_mock.assert_not_called()
        self.assertEqual(len(emitted[0]), 1)
        self.assertEqual(emitted[0][0]["source"], "MusicBrainz")

    def test_worker_itunes_only(self):
        """source=itunes calls itunes_fetcher.search and tags results."""
        it_result = [{"title": "Song", "artist": "A", "album": "", "year": "2020", "score": 80, "artwork_url": ""}]
        with patch("tag_fetcher.search", return_value=[]) as mb_mock, \
             patch("itunes_fetcher.search", return_value=it_result) as it_mock:
            worker = _FetchWorker("A", "Song", _SRC_ITUNES)
            emitted = []
            worker.finished.connect(emitted.append)
            worker.run()

        mb_mock.assert_not_called()
        it_mock.assert_called_once_with("A", "Song")
        self.assertEqual(len(emitted[0]), 1)
        self.assertEqual(emitted[0][0]["source"], "iTunes")

    def test_worker_both_merges_and_sorts(self):
        """source=both merges both sources and sorts by score descending."""
        mb_result = [{"title": "S", "artist": "A", "album": "", "year": "", "score": 70}]
        it_result = [{"title": "S", "artist": "A", "album": "", "year": "", "score": 95, "artwork_url": ""}]
        with patch("tag_fetcher.search", return_value=mb_result), \
             patch("itunes_fetcher.search", return_value=it_result):
            worker = _FetchWorker("A", "S", _SRC_BOTH)
            emitted = []
            worker.finished.connect(emitted.append)
            worker.run()

        results = emitted[0]
        self.assertEqual(len(results), 2)
        self.assertGreaterEqual(results[0]["score"], results[1]["score"])
        sources = {r["source"] for r in results}
        self.assertEqual(sources, {"MusicBrainz", "iTunes"})


# ---------------------------------------------------------------------------
# TagFetchDialog — file filtering (__init__)
# ---------------------------------------------------------------------------

class TestTagFetchDialogFiltering(unittest.TestCase):

    def test_filters_files_missing_title(self):
        """Files with no title are included in the queue."""
        files = [_file(title=None, artist="A")]
        dlg = _make_dialog(files)
        self.assertEqual(len(dlg._files), 1)

    def test_filters_files_missing_artist(self):
        """Files with no artist are included in the queue."""
        files = [_file(title="T", artist=None)]
        dlg = _make_dialog(files)
        self.assertEqual(len(dlg._files), 1)

    def test_excludes_files_with_both_tags(self):
        """Files that have both title and artist are excluded."""
        files = [_file(title="T", artist="A")]
        dlg = _make_dialog(files)
        self.assertEqual(len(dlg._files), 0)

    def test_empty_queue_disables_buttons(self):
        """When no files need tagging, apply and skip buttons are disabled."""
        manager = MagicMock()
        dlg = TagFetchDialog(manager, [_file(title="T", artist="A")])
        self.assertFalse(dlg._btn_apply.isEnabled())
        self.assertFalse(dlg._btn_skip.isEnabled())


# ---------------------------------------------------------------------------
# TagFetchDialog — _current_source()
# ---------------------------------------------------------------------------

class TestCurrentSource(unittest.TestCase):

    def test_returns_correct_identifier_for_each_combo_index(self):
        """Combo index 0/1/2 returns musicbrainz/itunes/both."""
        dlg = _make_dialog([])
        dlg._source_combo.setCurrentIndex(0)
        self.assertEqual(dlg._current_source(), _SRC_MB)
        dlg._source_combo.setCurrentIndex(1)
        self.assertEqual(dlg._current_source(), _SRC_ITUNES)
        dlg._source_combo.setCurrentIndex(2)
        self.assertEqual(dlg._current_source(), _SRC_BOTH)


# ---------------------------------------------------------------------------
# TagFetchDialog — _load_current() filename fallback
# ---------------------------------------------------------------------------

class TestLoadCurrentFallback(unittest.TestCase):

    def test_filename_used_when_no_tags(self):
        """When artist and title are both None, filename without extension is used."""
        files = [_file(filename="아이유 - 좋은날.mp3", title=None, artist=None)]
        dlg = _make_dialog(files)
        dlg._index = 0

        started_with = {}

        def capture_worker(artist, title, source):
            started_with["artist"] = artist
            started_with["title"] = title
            w = MagicMock()
            w.isRunning.return_value = False
            return w

        with patch("tag_fetch_dialog._FetchWorker", side_effect=capture_worker):
            dlg._load_current()

        self.assertIsNone(started_with["artist"])
        self.assertEqual(started_with["title"], "아이유 - 좋은날")

    def test_no_fallback_when_title_present(self):
        """When title is set, filename is not used as fallback."""
        files = [_file(filename="track.mp3", title="실제 제목", artist=None)]
        dlg = _make_dialog(files)
        dlg._index = 0

        started_with = {}

        def capture_worker(artist, title, source):
            started_with["title"] = title
            w = MagicMock()
            w.isRunning.return_value = False
            return w

        with patch("tag_fetch_dialog._FetchWorker", side_effect=capture_worker):
            dlg._load_current()

        self.assertEqual(started_with["title"], "실제 제목")


# ---------------------------------------------------------------------------
# TagFetchDialog — _on_fetch_done()
# ---------------------------------------------------------------------------

class TestOnFetchDone(unittest.TestCase):

    def _make_candidate(self, title="T", artist="A", album="Al", year="2020",
                        score=90, source="iTunes"):
        return {"title": title, "artist": artist, "album": album,
                "year": year, "score": score, "source": source}

    def test_populates_6_columns(self):
        """_on_fetch_done fills all 6 table columns per row."""
        dlg = _make_dialog([_file(title=None)])
        candidates = [self._make_candidate()]
        dlg._on_fetch_done(candidates)

        self.assertEqual(dlg._table.rowCount(), 1)
        self.assertEqual(dlg._table.item(0, 0).text(), "90")
        self.assertEqual(dlg._table.item(0, 1).text(), "T")
        self.assertEqual(dlg._table.item(0, 2).text(), "A")
        self.assertEqual(dlg._table.item(0, 3).text(), "Al")
        self.assertEqual(dlg._table.item(0, 4).text(), "2020")
        self.assertEqual(dlg._table.item(0, 5).text(), "iTunes")

    def test_empty_results_keeps_table_empty(self):
        """_on_fetch_done with no candidates leaves the table at 0 rows."""
        dlg = _make_dialog([_file(title=None)])
        dlg._on_fetch_done([])
        self.assertEqual(dlg._table.rowCount(), 0)

    def test_apply_enabled_after_results(self):
        """Apply button becomes enabled once candidates are loaded."""
        dlg = _make_dialog([_file(title=None)])
        dlg._on_fetch_done([self._make_candidate()])
        self.assertTrue(dlg._btn_apply.isEnabled())


# ---------------------------------------------------------------------------
# TagFetchDialog — _on_apply() / _on_skip()
# ---------------------------------------------------------------------------

class TestApplySkip(unittest.TestCase):

    def _dialog_with_one_file(self):
        """Return a dialog with one queued file and one result row loaded."""
        f = _file(filename="song.mp3", title=None, artist=None, path="/tmp/song.mp3")
        dlg = _make_dialog([f])
        dlg._index = 0
        # Pre-populate one result row.
        dlg._on_fetch_done([{
            "title": "제목", "artist": "가수", "album": "앨범",
            "year": "2021", "score": 95, "source": "iTunes",
        }])
        return dlg

    def test_apply_calls_update_file_tags(self):
        """_on_apply writes selected row's tags via manager.update_file_tags."""
        dlg = self._dialog_with_one_file()
        with patch.object(dlg, "_load_current"):
            dlg._on_apply()
        dlg._manager.update_file_tags.assert_called_once_with(
            "/tmp/song.mp3", "제목", "가수", "앨범"
        )

    def test_apply_advances_index(self):
        """_on_apply increments _index."""
        dlg = self._dialog_with_one_file()
        with patch.object(dlg, "_load_current"):
            dlg._on_apply()
        self.assertEqual(dlg._index, 1)

    def test_skip_advances_without_update(self):
        """_on_skip increments _index without calling update_file_tags."""
        dlg = self._dialog_with_one_file()
        with patch.object(dlg, "_load_current"):
            dlg._on_skip()
        dlg._manager.update_file_tags.assert_not_called()
        self.assertEqual(dlg._index, 1)


# ---------------------------------------------------------------------------
# TagFetchDialog — keyword input pre-fill and _on_search_clicked()
# ---------------------------------------------------------------------------

class TestKeywordSearch(unittest.TestCase):

    def test_keyword_prefilled_from_tags(self):
        """_load_current pre-fills the keyword input with available tag."""
        files = [_file(filename="track.mp3", title="Dynamite", artist=None)]
        dlg = _make_dialog(files)
        dlg._index = 0

        with patch("tag_fetch_dialog._FetchWorker") as mock_worker_cls:
            mock_worker_cls.return_value.isRunning.return_value = False
            dlg._load_current()

        self.assertIn("Dynamite", dlg._keyword_edit.text())

    def test_keyword_prefilled_from_filename_when_no_tags(self):
        """_load_current pre-fills the keyword input with filename when tags absent."""
        files = [_file(filename="아이유 - 좋은날.mp3", title=None, artist=None)]
        dlg = _make_dialog(files)
        dlg._index = 0

        with patch("tag_fetch_dialog._FetchWorker") as mock_worker_cls:
            mock_worker_cls.return_value.isRunning.return_value = False
            dlg._load_current()

        self.assertEqual(dlg._keyword_edit.text(), "아이유 - 좋은날")

    def test_search_clicked_uses_keyword_input(self):
        """_on_search_clicked passes keyword input text as title to worker."""
        dlg = _make_dialog([_file(title=None)])
        dlg._keyword_edit.setText("검색할 곡 이름")

        started_with = {}

        def capture_worker(artist, title, source):
            started_with["artist"] = artist
            started_with["title"]  = title
            w = MagicMock()
            w.isRunning.return_value = False
            return w

        with patch("tag_fetch_dialog._FetchWorker", side_effect=capture_worker):
            dlg._on_search_clicked()

        self.assertIsNone(started_with["artist"])
        self.assertEqual(started_with["title"], "검색할 곡 이름")

    def test_search_clicked_ignores_empty_input(self):
        """_on_search_clicked does nothing when keyword input is blank."""
        dlg = _make_dialog([_file(title=None)])
        dlg._keyword_edit.setText("   ")

        with patch("tag_fetch_dialog._FetchWorker") as mock_worker_cls:
            dlg._on_search_clicked()

        mock_worker_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
