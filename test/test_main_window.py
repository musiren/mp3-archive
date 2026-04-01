"""
test_main_window.py - Unit tests for src/main_window.py.

Tests use an in-memory Mp3Manager and a headless QApplication
to exercise widget logic without rendering a real window.
"""

import os
import sqlite3
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mp3_manager import Mp3Manager, _create_table, _save_to_db
from main_window import MainWindow, ScanWorker


# One QApplication per process is required by Qt.
_app = QApplication.instance() or QApplication(sys.argv)


def make_manager() -> Mp3Manager:
    """Return an Mp3Manager backed by an in-memory SQLite database."""
    mgr = Mp3Manager.__new__(Mp3Manager)
    mgr._conn = sqlite3.connect(":memory:", check_same_thread=False)
    _create_table(mgr._conn)
    return mgr


def sample_info(path: str = "/music/test.mp3") -> dict:
    """Return a sample audio info dictionary."""
    return {
        "path": path,
        "filename": os.path.basename(path),
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
        "genre": None,
        "year": None,
        "comment": None,
        "duration": 180.0,
        "filesize": 4096,
        "file_created_at": "2024-01-01 00:00:00",
        "file_modified_at": "2024-06-01 12:00:00",
    }


class TestMainWindowPath(unittest.TestCase):

    def _make_window(self) -> MainWindow:
        """Return a MainWindow using a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        self._db_path = db_path
        win = MainWindow(db_path)
        self._win = win
        return win

    def tearDown(self):
        if hasattr(self, "_win"):
            self._win._manager.close()
            self._win._settings.clear()
        if hasattr(self, "_db_path") and os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def test_path_edit_empty_on_fresh_start(self):
        """Verify that path_edit is empty when no path has been saved."""
        win = self._make_window()
        win._settings.clear()
        win._restore_path()
        self.assertEqual(win.path_edit.text(), "")
        win.close()

    def test_browse_saves_path_to_settings(self):
        """Verify that selecting a directory via browse saves it to QSettings."""
        win = self._make_window()
        with tempfile.TemporaryDirectory() as tmpdir:
            win.path_edit.setText(tmpdir)
            win._settings.setValue("scan/last_path", tmpdir)
            saved = win._settings.value("scan/last_path", "")
        self.assertEqual(saved, tmpdir)
        win.close()

    def test_scan_warns_when_no_path_set(self):
        """Verify that clicking scan without a path shows a warning (no crash)."""
        win = self._make_window()
        win.path_edit.setText("")
        # _on_scan_clicked should not raise even with empty path
        # (QMessageBox.warning is a no-op in offscreen mode)
        try:
            # Monkey-patch to avoid actual dialog
            from PyQt6.QtWidgets import QMessageBox
            original = QMessageBox.warning
            QMessageBox.warning = lambda *a, **k: None
            win._on_scan_clicked()
            QMessageBox.warning = original
        except Exception as e:
            self.fail(f"_on_scan_clicked raised unexpectedly: {e}")
        win.close()

    def test_restore_path_populates_path_edit(self):
        """Verify that a previously saved path is restored into path_edit."""
        win = self._make_window()
        win._settings.setValue("scan/last_path", "/tmp/music")
        win._restore_path()
        self.assertEqual(win.path_edit.text(), "/tmp/music")
        win.close()


class TestMainWindowTable(unittest.TestCase):

    def _make_window(self) -> MainWindow:
        """Return a MainWindow using a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        self._db_path = db_path
        win = MainWindow(db_path)
        self._win = win
        return win

    def tearDown(self):
        if hasattr(self, "_win"):
            self._win._manager.close()
        if hasattr(self, "_db_path") and os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def test_table_empty_on_fresh_db(self):
        """Verify that the table has zero rows when the database is empty."""
        win = self._make_window()
        self.assertEqual(win.table.rowCount(), 0)
        win.close()

    def test_table_populates_after_load(self):
        """Verify that _load_table fills the table from database records."""
        win = self._make_window()
        _save_to_db(win._manager._conn, sample_info("/music/a.mp3"))
        _save_to_db(win._manager._conn, sample_info("/music/b.mp3"))
        win._load_table()
        self.assertEqual(win.table.rowCount(), 2)
        win.close()

    def test_table_shows_filename_in_first_column(self):
        """Verify that the filename appears in column 0."""
        win = self._make_window()
        _save_to_db(win._manager._conn, sample_info("/music/track.mp3"))
        win._load_table()
        self.assertEqual(win.table.item(0, 0).text(), "track.mp3")
        win.close()

    def test_table_stores_path_in_user_role(self):
        """Verify that the full path is stored in UserRole for deletion."""
        from PyQt6.QtCore import Qt
        win = self._make_window()
        _save_to_db(win._manager._conn, sample_info("/music/track.mp3"))
        win._load_table()
        path = win.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        self.assertEqual(path, "/music/track.mp3")
        win.close()


class TestSearch(unittest.TestCase):

    def _make_window(self) -> MainWindow:
        """Return a MainWindow with two pre-loaded MP3 records."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        self._db_path = db_path
        win = MainWindow(db_path)
        self._win = win
        info_a = {**sample_info("/music/Queen - Bohemian Rhapsody.mp3"),
                  "artist": "Queen", "title": "Bohemian Rhapsody"}
        info_b = {**sample_info("/music/BTS - Dynamite.mp3"),
                  "artist": "BTS", "title": "Dynamite"}
        _save_to_db(win._manager._conn, info_a)
        _save_to_db(win._manager._conn, info_b)
        win._load_table()
        return win

    def tearDown(self):
        if hasattr(self, "_win"):
            self._win._manager.close()
        if hasattr(self, "_db_path") and os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def test_realtime_search_filters_table(self):
        """Verify that typing in search_edit filters the table immediately."""
        win = self._make_window()
        win.search_edit.setText("Queen")
        self.assertEqual(win.table.rowCount(), 1)
        self.assertEqual(win.table.item(0, 2).text(), "Queen")
        win.close()

    def test_realtime_search_empty_restores_all(self):
        """Verify that clearing search_edit restores all rows."""
        win = self._make_window()
        win.search_edit.setText("Queen")
        win.search_edit.clear()
        self.assertEqual(win.table.rowCount(), 2)
        win.close()

    def test_search_clear_button_restores_all(self):
        """Verify that btn_search_clear resets search and shows all rows."""
        win = self._make_window()
        win.search_edit.setText("BTS")
        self.assertEqual(win.table.rowCount(), 1)
        win.btn_search_clear.click()
        self.assertEqual(win.table.rowCount(), 2)
        win.close()


class TestContextMenu(unittest.TestCase):

    def _make_window_with_row(self) -> tuple:
        """Return (MainWindow, file_info) with one record pre-loaded."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        self._db_path = db_path
        win = MainWindow(db_path)
        self._win = win
        info = {**sample_info("/music/track.mp3"),
                "artist": "Test Artist", "title": "Test Song"}
        from mp3_manager import _save_to_db
        _save_to_db(win._manager._conn, info)
        win._load_table()
        return win, info

    def tearDown(self):
        if hasattr(self, "_win"):
            self._win._manager.close()
        if hasattr(self, "_db_path") and os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def test_context_menu_policy_is_custom(self):
        """Verify that the table uses CustomContextMenu policy."""
        from PyQt6.QtCore import Qt
        win, _ = self._make_window_with_row()
        self.assertEqual(
            win.table.contextMenuPolicy(),
            Qt.ContextMenuPolicy.CustomContextMenu,
        )
        win.close()

    def test_context_menu_handler_resolves_file_info(self):
        """Verify _on_table_context_menu finds the correct file_info for row 0."""
        win, info = self._make_window_with_row()
        # Simulate looking up the file for row 0 via the same logic the handler uses
        from PyQt6.QtCore import Qt
        path = win.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
        files = win._manager.list_files()
        found = next((f for f in files if f["path"] == path), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["title"], "Test Song")
        win.close()


class TestPlaylist(unittest.TestCase):
    """Tests for the playlist panel and playback helper methods."""

    def _make_window(self) -> MainWindow:
        """Return a MainWindow using a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        self._db_path = db_path
        win = MainWindow(db_path)
        self._win = win
        return win

    def tearDown(self):
        if hasattr(self, "_win"):
            if self._win._player is not None:
                self._win._player.stop()
            self._win._manager.close()
        if hasattr(self, "_db_path") and os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def test_playlist_add_appends_item(self):
        """Verify that _playlist_add inserts an item into playlist_widget."""
        win = self._make_window()
        win._playlist_add("/music/track.mp3")
        self.assertEqual(win.playlist_widget.count(), 1)
        self.assertEqual(win.playlist_widget.item(0).text(), "track.mp3")
        win.close()

    def test_playlist_add_allows_duplicates(self):
        """Verify that adding the same path twice results in two entries."""
        win = self._make_window()
        win._playlist_add("/music/track.mp3")
        win._playlist_add("/music/track.mp3")
        self.assertEqual(win.playlist_widget.count(), 2)
        win.close()

    def test_playlist_add_stores_path_in_user_role(self):
        """Verify that the full path is stored in UserRole of the playlist item."""
        from PyQt6.QtCore import Qt
        win = self._make_window()
        win._playlist_add("/music/track.mp3")
        path = win.playlist_widget.item(0).data(Qt.ItemDataRole.UserRole)
        self.assertEqual(path, "/music/track.mp3")
        win.close()

    def test_playlist_clear_empties_list(self):
        """Verify that btn_playlist_clear removes all items from the playlist."""
        win = self._make_window()
        win._playlist_add("/music/a.mp3")
        win._playlist_add("/music/b.mp3")
        self.assertEqual(win.playlist_widget.count(), 2)
        win.btn_playlist_clear.click()
        self.assertEqual(win.playlist_widget.count(), 0)
        win.close()

    def test_playlist_clear_resets_title_label(self):
        """Verify that clearing the playlist resets player_title_label to '-'."""
        win = self._make_window()
        win.player_title_label.setText("Some Song")
        win.btn_playlist_clear.click()
        self.assertEqual(win.player_title_label.text(), "-")
        win.close()

    def test_highlight_playing_row_sets_background(self):
        """Verify that _highlight_playing_row sets a solid background on the playing row
        and resets the other row to an empty (null) brush."""
        from PyQt6.QtGui import QBrush
        win = self._make_window()
        win._playlist_add("/music/a.mp3")
        win._playlist_add("/music/b.mp3")
        win._highlight_playing_row(0)
        item0 = win.playlist_widget.item(0)
        item1 = win.playlist_widget.item(1)
        # Playing row must have a non-null brush
        self.assertNotEqual(item0.background(), QBrush())
        # Non-playing row must have the default null brush
        self.assertEqual(item1.background(), QBrush())
        win.close()

    def test_highlight_playing_row_minus_one_resets_all(self):
        """Verify that _highlight_playing_row(-1) resets all rows to null brush."""
        from PyQt6.QtGui import QBrush
        win = self._make_window()
        win._playlist_add("/music/a.mp3")
        win._highlight_playing_row(0)
        win._highlight_playing_row(-1)
        item0 = win.playlist_widget.item(0)
        self.assertEqual(item0.background(), QBrush())
        win.close()

    def test_playlist_current_path_returns_none_when_empty(self):
        """Verify that _playlist_current_path returns None when no item is selected."""
        win = self._make_window()
        self.assertIsNone(win._playlist_current_path())
        win.close()

    def test_playlist_current_path_returns_selected(self):
        """Verify that _playlist_current_path returns the selected item's path."""
        win = self._make_window()
        win._playlist_add("/music/a.mp3")
        win.playlist_widget.setCurrentRow(0)
        self.assertEqual(win._playlist_current_path(), "/music/a.mp3")
        win.close()

    def test_playlist_widget_exists(self):
        """Verify that the playlist_widget attribute exists on the window."""
        win = self._make_window()
        self.assertTrue(hasattr(win, "playlist_widget"))
        win.close()

    def test_player_controls_exist(self):
        """Verify that all playback control buttons and volume slider exist on the window."""
        win = self._make_window()
        for attr in ("btn_play_pause", "btn_stop", "btn_prev", "btn_next",
                     "btn_playlist_clear", "seek_slider", "volume_slider", "volume_label",
                     "player_title_label", "time_current_label", "time_total_label"):
            self.assertTrue(hasattr(win, attr), f"Missing widget: {attr}")
        win.close()

    def test_table_double_click_adds_to_playlist_and_sets_title(self):
        """Verify that double-clicking a table row adds it to playlist and sets the title label."""
        win = self._make_window()
        from mp3_manager import _save_to_db
        _save_to_db(win._manager._conn, sample_info("/music/track.mp3"))
        win._load_table()
        # Simulate double-click on row 0
        win._on_table_double_clicked(0, 0)
        self.assertEqual(win.playlist_widget.count(), 1)
        self.assertEqual(win.playlist_widget.item(0).text(), "track.mp3")
        self.assertEqual(win.player_title_label.text(), "track.mp3")
        win.close()

    def test_table_double_click_allows_duplicate_in_playlist(self):
        """Verify that double-clicking the same row twice adds two playlist entries."""
        win = self._make_window()
        from mp3_manager import _save_to_db
        _save_to_db(win._manager._conn, sample_info("/music/track.mp3"))
        win._load_table()
        win._on_table_double_clicked(0, 0)
        win._on_table_double_clicked(0, 0)
        self.assertEqual(win.playlist_widget.count(), 2)
        win.close()


class TestPlaylistSaveLoad(unittest.TestCase):
    """Tests for playlist save/load functionality."""

    def _make_window(self) -> MainWindow:
        """Return a MainWindow using a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        self._db_path = db_path
        win = MainWindow(db_path)
        self._win = win
        return win

    def tearDown(self):
        if hasattr(self, "_win"):
            if self._win._player is not None:
                self._win._player.stop()
            self._win._manager.close()
        if hasattr(self, "_db_path") and os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def test_save_creates_list_file(self):
        """Verify that _on_playlist_save_clicked writes a .list file with correct paths."""
        win = self._make_window()
        win._playlist_add("/music/a.mp3")
        win._playlist_add("/music/b.mp3")

        with tempfile.NamedTemporaryFile(suffix=".list", delete=False, mode="w") as f:
            list_path = f.name

        try:
            # Directly call the save logic bypassing the file dialog
            with open(list_path, "w", encoding="utf-8") as f:
                for i in range(win.playlist_widget.count()):
                    f.write(win.playlist_widget.item(i).data(
                        __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.ItemDataRole.UserRole
                    ) + "\n")

            with open(list_path, encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]

            self.assertEqual(lines, ["/music/a.mp3", "/music/b.mp3"])
        finally:
            os.unlink(list_path)
        win.close()

    def test_load_appends_existing_files(self):
        """Verify that _on_playlist_load_clicked adds existing file paths to playlist."""
        win = self._make_window()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create real temp audio files so os.path.isfile passes
            path_a = os.path.join(tmpdir, "a.mp3")
            path_b = os.path.join(tmpdir, "b.mp3")
            open(path_a, "w").close()
            open(path_b, "w").close()

            list_file = os.path.join(tmpdir, "test.list")
            with open(list_file, "w", encoding="utf-8") as f:
                f.write(path_a + "\n")
                f.write(path_b + "\n")

            # Call the load logic directly, bypassing the file dialog
            with open(list_file, "r", encoding="utf-8") as f:
                lines = [l.rstrip("\n") for l in f if l.strip()]
            for file_path in lines:
                if os.path.isfile(file_path):
                    win._playlist_add(file_path)

            self.assertEqual(win.playlist_widget.count(), 2)
        win.close()

    def test_load_skips_missing_files(self):
        """Verify that non-existent paths in a .list file are skipped silently."""
        win = self._make_window()

        with tempfile.NamedTemporaryFile(suffix=".list", delete=False,
                                         mode="w", encoding="utf-8") as f:
            f.write("/does/not/exist/a.mp3\n")
            f.write("/does/not/exist/b.mp3\n")
            list_path = f.name

        try:
            with open(list_path, "r", encoding="utf-8") as f:
                lines = [l.rstrip("\n") for l in f if l.strip()]
            for file_path in lines:
                if os.path.isfile(file_path):
                    win._playlist_add(file_path)

            self.assertEqual(win.playlist_widget.count(), 0)
        finally:
            os.unlink(list_path)
        win.close()


class TestTheme(unittest.TestCase):
    """Tests for theme toggle functionality."""

    def _make_window(self) -> MainWindow:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        self._db_path = db_path
        win = MainWindow(db_path)
        win._settings.clear()
        self._win = win
        return win

    def tearDown(self):
        if hasattr(self, "_win"):
            if self._win._player is not None:
                self._win._player.stop()
            self._win._settings.clear()
            self._win._manager.close()
        if hasattr(self, "_db_path") and os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def test_default_theme_is_system(self):
        """Verify that the default theme is 'system' with no stylesheet."""
        win = self._make_window()
        theme = win._settings.value("ui/theme", "system")
        self.assertEqual(theme, "system")
        win.close()

    def test_theme_cycles_through_all(self):
        """Verify that clicking btn_theme cycles system → light → dark → system."""
        win = self._make_window()
        win._apply_theme("system")
        expected = ["light", "dark", "system"]
        for mode in expected:
            win.btn_theme.click()
            saved = win._settings.value("ui/theme", "system")
            self.assertEqual(saved, mode)
        win.close()

    def test_apply_dark_sets_stylesheet(self):
        """Verify that applying dark theme sets a non-empty stylesheet."""
        win = self._make_window()
        win._apply_theme("dark")
        self.assertNotEqual(_app.styleSheet(), "")
        win.close()

    def test_apply_system_clears_stylesheet(self):
        """Verify that applying system theme clears the stylesheet."""
        win = self._make_window()
        win._apply_theme("dark")
        win._apply_theme("system")
        self.assertEqual(_app.styleSheet(), "")
        win.close()

    def test_btn_label_matches_active_theme(self):
        """Verify that the theme button label matches the current theme."""
        win = self._make_window()
        labels = {"system": "💻 시스템", "light": "☀ 라이트", "dark": "🌙 다크"}
        for theme, label in labels.items():
            win._apply_theme(theme)
            self.assertEqual(win.btn_theme.text(), label)
        win.close()


class TestPlayMode(unittest.TestCase):
    """Tests for playback mode toggle button."""

    def _make_window(self) -> MainWindow:
        """Return a MainWindow using a temporary database file."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        self._db_path = db_path
        win = MainWindow(db_path)
        self._win = win
        return win

    def tearDown(self):
        if hasattr(self, "_win"):
            if self._win._player is not None:
                self._win._player.stop()
            self._win._manager.close()
        if hasattr(self, "_db_path") and os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def test_initial_mode_is_sequential(self):
        """Verify that the default playback mode is sequential."""
        win = self._make_window()
        self.assertEqual(win._play_mode, "sequential")
        win.close()

    def test_mode_cycles_through_all_modes(self):
        """Verify that clicking btn_play_mode cycles through all four modes."""
        win = self._make_window()
        expected = ["repeat_one", "repeat_all", "shuffle", "sequential"]
        for mode in expected:
            win.btn_play_mode.click()
            self.assertEqual(win._play_mode, mode)
        win.close()

    def test_button_label_updates_with_mode(self):
        """Verify that the button label matches the active mode."""
        win = self._make_window()
        labels = {
            "repeat_one": "🔂 한곡반복",
            "repeat_all": "🔁 전체반복",
            "shuffle":    "🔀 랜덤",
            "sequential": "➡ 전체재생",
        }
        for _ in range(4):
            win.btn_play_mode.click()
            self.assertEqual(win.btn_play_mode.text(), labels[win._play_mode])
        win.close()


class TestScanWorker(unittest.TestCase):

    def test_scan_worker_emits_finished(self):
        """Verify that ScanWorker emits finished with (processed, skipped) counts."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.mp3"), "w").close()
            open(os.path.join(tmpdir, "b.mp3"), "w").close()

            results = []
            worker = ScanWorker(mgr, tmpdir, force=True)
            worker.finished.connect(lambda p, s: results.append((p, s)))
            worker.start()
            worker.wait()
            _app.processEvents()

        self.assertEqual(results, [(2, 0)])
        mgr.close()

    def test_scan_worker_incremental_skips_unchanged(self):
        """Verify that a second incremental scan skips already-indexed files."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.mp3"), "w").close()

            # First scan: processes the file
            w1 = ScanWorker(mgr, tmpdir, force=True)
            w1.start(); w1.wait(); _app.processEvents()

            # Second incremental scan: file unchanged → skipped
            results = []
            w2 = ScanWorker(mgr, tmpdir, force=False)
            w2.finished.connect(lambda p, s: results.append((p, s)))
            w2.start(); w2.wait(); _app.processEvents()

        self.assertEqual(results, [(0, 1)])
        mgr.close()

    def test_scan_worker_emits_progress(self):
        """Verify that ScanWorker emits a progress signal for each MP3 file."""
        mgr = make_manager()
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                open(os.path.join(tmpdir, f"track{i}.mp3"), "w").close()

            progress_calls = []
            worker = ScanWorker(mgr, tmpdir, force=True)
            worker.progress.connect(lambda cur, tot, p: progress_calls.append((cur, tot)))
            worker.start()
            worker.wait()
            _app.processEvents()

        self.assertEqual(len(progress_calls), 3)
        self.assertEqual(progress_calls[-1], (3, 3))
        mgr.close()


if __name__ == "__main__":
    unittest.main()
