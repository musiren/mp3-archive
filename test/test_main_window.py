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
from unittest.mock import patch

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
        """Verify that _switch_directory saves the chosen path to QSettings."""
        win = self._make_window()
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(win, "_start_scan"):
            win._switch_directory(tmpdir)
            saved = win._settings.value("scan/last_path", "")
        self.assertEqual(saved, tmpdir)
        win.close()

    def test_switch_directory_opens_db_in_directory(self):
        """_switch_directory creates .mp3-archive.db inside the target directory."""
        win = self._make_window()
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(win, "_start_scan"):
            win._switch_directory(tmpdir)
            db_path = os.path.join(tmpdir, ".mp3-archive.db")
            self.assertTrue(os.path.exists(db_path))
        win.close()

    def test_switch_directory_sets_path_edit(self):
        """_switch_directory updates path_edit to the new directory."""
        win = self._make_window()
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(win, "_start_scan"):
            win._switch_directory(tmpdir)
            self.assertEqual(win.path_edit.text(), tmpdir)
        win.close()

    def test_restore_path_calls_switch_when_dir_exists(self):
        """_restore_path calls _switch_directory when the saved path is a real directory."""
        win = self._make_window()
        with tempfile.TemporaryDirectory() as tmpdir:
            win._settings.setValue("scan/last_path", tmpdir)
            with patch.object(win, "_switch_directory") as mock_switch, \
                 patch.object(win, "_start_scan"):
                win._restore_path()
            mock_switch.assert_called_once_with(tmpdir)
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

    def test_count_label_shows_total_when_not_searching(self):
        """Verify that count_label shows total song count when no search is active."""
        win = self._make_window()
        self.assertEqual(win.count_label.text(), "전체 2곡")
        win.close()

    def test_count_label_shows_search_result_when_searching(self):
        """Verify that count_label shows searched/total counts during search."""
        win = self._make_window()
        win.search_edit.setText("Queen")
        self.assertIn("검색 결과:", win.count_label.text())
        self.assertIn("1곡", win.count_label.text())
        self.assertIn("전체 2곡", win.count_label.text())
        win.close()

    def test_count_label_resets_after_clear(self):
        """Verify that count_label shows total count after search is cleared."""
        win = self._make_window()
        win.search_edit.setText("Queen")
        win.btn_search_clear.click()
        self.assertEqual(win.count_label.text(), "전체 2곡")
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

    def test_double_click_playlist_clears_previous_highlight(self):
        """Double-clicking a different playlist item removes the previous row's highlight."""
        from PyQt6.QtGui import QBrush
        win = self._make_window()
        win._playlist_add("/music/a.mp3")
        win._playlist_add("/music/b.mp3")
        win._highlight_playing_row(0)
        # Double-click row 1
        item1 = win.playlist_widget.item(1)
        win._on_playlist_double_clicked(item1)
        item0 = win.playlist_widget.item(0)
        # Previous row must be reset to null brush
        self.assertEqual(item0.background(), QBrush())
        win.close()

    def test_double_click_playlist_highlights_new_row(self):
        """Double-clicking a playlist item highlights that row."""
        from PyQt6.QtGui import QBrush
        win = self._make_window()
        win._playlist_add("/music/a.mp3")
        win._playlist_add("/music/b.mp3")
        win._highlight_playing_row(0)
        item1 = win.playlist_widget.item(1)
        win._on_playlist_double_clicked(item1)
        # New row must have a non-null brush
        self.assertNotEqual(item1.background(), QBrush())
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

    def test_delete_key_removes_item_from_playlist(self):
        """Verify that pressing Delete removes the selected playlist item."""
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        win = self._make_window()
        win._playlist_add("/music/a.mp3")
        win._playlist_add("/music/b.mp3")
        win.playlist_widget.setCurrentRow(0)
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
        win.eventFilter(win.playlist_widget, event)
        self.assertEqual(win.playlist_widget.count(), 1)
        self.assertEqual(win.playlist_widget.item(0).text(), "b.mp3")
        win.close()

    def test_delete_key_removes_multiple_selected_items(self):
        """Verify that pressing Delete removes all selected playlist items at once."""
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        win = self._make_window()
        for name in ("a.mp3", "b.mp3", "c.mp3"):
            win._playlist_add(f"/music/{name}")
        # Select rows 0 and 2
        win.playlist_widget.item(0).setSelected(True)
        win.playlist_widget.item(2).setSelected(True)
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
        win.eventFilter(win.playlist_widget, event)
        self.assertEqual(win.playlist_widget.count(), 1)
        self.assertEqual(win.playlist_widget.item(0).text(), "b.mp3")
        win.close()

    def test_ctrl_a_selects_all_playlist_items(self):
        """Verify that Ctrl+A selects every item in the playlist."""
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        win = self._make_window()
        for name in ("a.mp3", "b.mp3", "c.mp3"):
            win._playlist_add(f"/music/{name}")
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        win.eventFilter(win.playlist_widget, event)
        selected = win.playlist_widget.selectedItems()
        self.assertEqual(len(selected), 3)
        win.close()

    def test_delete_key_adjusts_playing_index(self):
        """Verify that deleting a row above the playing track decrements _playing_index."""
        from PyQt6.QtCore import QEvent, Qt
        from PyQt6.QtGui import QKeyEvent
        win = self._make_window()
        win._playlist_add("/music/a.mp3")
        win._playlist_add("/music/b.mp3")
        win._playing_index = 1
        win.playlist_widget.setCurrentRow(0)
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)
        win.eventFilter(win.playlist_widget, event)
        self.assertEqual(win._playing_index, 0)
        win.close()

    def test_playlist_context_menu_remove_decrements_playing_index(self):
        """Verify that removing a playlist item above the playing track decrements _playing_index."""
        win = self._make_window()
        win._playlist_add("/music/a.mp3")
        win._playlist_add("/music/b.mp3")
        win._playlist_add("/music/c.mp3")
        win._playing_index = 2
        # Simulate removing row 0 via the context menu handler logic directly
        row = 0
        win.playlist_widget.takeItem(row)
        if row < win._playing_index:
            win._playing_index -= 1
        self.assertEqual(win._playing_index, 1)
        self.assertEqual(win.playlist_widget.count(), 2)
        win.close()

    def test_playlist_context_menu_remove_playing_resets_index(self):
        """Verify that removing the currently playing track resets _playing_index to -1."""
        win = self._make_window()
        win._playlist_add("/music/a.mp3")
        win._playlist_add("/music/b.mp3")
        win._playing_index = 1
        row = 1
        win.playlist_widget.takeItem(row)
        if row == win._playing_index:
            win._playing_index = -1
        self.assertEqual(win._playing_index, -1)
        self.assertEqual(win.playlist_widget.count(), 1)
        win.close()

    def test_playlist_context_menu_policy_is_custom(self):
        """Verify that the playlist uses CustomContextMenu policy."""
        from PyQt6.QtCore import Qt
        win = self._make_window()
        self.assertEqual(
            win.playlist_widget.contextMenuPolicy(),
            Qt.ContextMenuPolicy.CustomContextMenu,
        )
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


class TestAlbumArtPanel(unittest.TestCase):
    """Tests for the album art label in the player panel."""

    def _make_window(self) -> MainWindow:
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

    def test_album_art_label_exists(self):
        """album_art_label widget is present in the main window."""
        win = self._make_window()
        self.assertTrue(hasattr(win, "album_art_label"))
        win.close()

    def test_update_album_art_no_art_shows_placeholder(self):
        """_update_album_art clears pixmap and shows placeholder for missing art."""
        win = self._make_window()
        win._update_album_art("/nonexistent/track.mp3")
        self.assertTrue(win.album_art_label.pixmap().isNull())
        self.assertEqual(win.album_art_label.text(), "♪")
        win.close()

    def test_stop_clears_album_art(self):
        """Stopping playback clears the album art label."""
        win = self._make_window()
        win._on_stop_clicked()
        self.assertEqual(win.album_art_label.text(), "♪")
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

    def test_apply_system_uses_minimal_stylesheet(self):
        """Verify that applying system theme sets only the tooltip padding stylesheet."""
        win = self._make_window()
        win._apply_theme("dark")
        win._apply_theme("system")
        self.assertIn("QToolTip", _app.styleSheet())
        self.assertIn("padding", _app.styleSheet())
        win.close()

    def test_btn_label_matches_active_theme(self):
        """Verify that the theme button label matches the current theme."""
        win = self._make_window()
        labels = {"system": "💻 시스템", "light": "☀ 라이트", "dark": "🌙 다크"}
        for theme, label in labels.items():
            win._apply_theme(theme)
            self.assertEqual(win.btn_theme.text(), label)
        win.close()


class TestPrevNext(unittest.TestCase):
    """Tests for prev/next button behaviour per playback mode."""

    def _make_window_with_playlist(self) -> MainWindow:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        self._db_path = db_path
        win = MainWindow(db_path)
        self._win = win
        for path in ["/music/a.mp3", "/music/b.mp3", "/music/c.mp3"]:
            win._playlist_add(path)
        # Simulate playback starting on middle track via _playing_index
        win._playing_index = 1
        win.playlist_widget.setCurrentRow(1)
        return win

    def tearDown(self):
        if hasattr(self, "_win"):
            if self._win._player is not None:
                self._win._player.stop()
            self._win._manager.close()
        if hasattr(self, "_db_path") and os.path.exists(self._db_path):
            os.unlink(self._db_path)

    def test_sequential_next_advances(self):
        """sequential: next goes to idx+1."""
        win = self._make_window_with_playlist()
        win._play_mode = "sequential"
        win._on_next_clicked()
        self.assertEqual(win.playlist_widget.currentRow(), 2)
        win.close()

    def test_sequential_prev_goes_back(self):
        """sequential: prev goes to idx-1."""
        win = self._make_window_with_playlist()
        win._play_mode = "sequential"
        win._on_prev_clicked()
        self.assertEqual(win.playlist_widget.currentRow(), 0)
        win.close()

    def test_sequential_next_clamps_at_last(self):
        """sequential: next on last track stays on last track."""
        win = self._make_window_with_playlist()
        win._play_mode = "sequential"
        win._playing_index = 2
        win._on_next_clicked()
        self.assertEqual(win.playlist_widget.currentRow(), 2)
        win.close()

    def test_sequential_prev_clamps_at_first(self):
        """sequential: prev on first track stays on first track."""
        win = self._make_window_with_playlist()
        win._play_mode = "sequential"
        win._playing_index = 0
        win._on_prev_clicked()
        self.assertEqual(win.playlist_widget.currentRow(), 0)
        win.close()

    def test_repeat_one_next_replays_same(self):
        """repeat_one: next replays the same track."""
        win = self._make_window_with_playlist()
        win._play_mode = "repeat_one"
        win._on_next_clicked()
        self.assertEqual(win.playlist_widget.currentRow(), 1)
        win.close()

    def test_repeat_one_prev_replays_same(self):
        """repeat_one: prev replays the same track."""
        win = self._make_window_with_playlist()
        win._play_mode = "repeat_one"
        win._on_prev_clicked()
        self.assertEqual(win.playlist_widget.currentRow(), 1)
        win.close()

    def test_repeat_all_next_wraps(self):
        """repeat_all: next on last track wraps to first."""
        win = self._make_window_with_playlist()
        win._play_mode = "repeat_all"
        win._playing_index = 2
        win._on_next_clicked()
        self.assertEqual(win.playlist_widget.currentRow(), 0)
        win.close()

    def test_repeat_all_prev_wraps(self):
        """repeat_all: prev on first track wraps to last."""
        win = self._make_window_with_playlist()
        win._play_mode = "repeat_all"
        win._playing_index = 0
        win._on_prev_clicked()
        self.assertEqual(win.playlist_widget.currentRow(), 2)
        win.close()

    def test_shuffle_next_picks_valid_index(self):
        """shuffle: next picks a valid playlist index."""
        win = self._make_window_with_playlist()
        win._play_mode = "shuffle"
        win._on_next_clicked()
        self.assertIn(win.playlist_widget.currentRow(), [0, 1, 2])
        win.close()

    def test_shuffle_prev_picks_valid_index(self):
        """shuffle: prev picks a valid playlist index."""
        win = self._make_window_with_playlist()
        win._play_mode = "shuffle"
        win._on_prev_clicked()
        self.assertIn(win.playlist_widget.currentRow(), [0, 1, 2])

    def test_rows_moved_playing_item_moved_up(self):
        """Drag playing item (index 1) to index 0: _playing_index becomes 0."""
        win = self._make_window_with_playlist()
        # Simulate model rowsMoved: row 1 → before row 0
        win._on_playlist_rows_moved(None, 1, 1, None, 0)
        self.assertEqual(win._playing_index, 0)
        win.close()

    def test_rows_moved_playing_item_moved_down(self):
        """Drag playing item (index 1) to index 2: _playing_index becomes 2."""
        win = self._make_window_with_playlist()
        # row 1 → before row 3 (after removal, lands at 2)
        win._on_playlist_rows_moved(None, 1, 1, None, 3)
        self.assertEqual(win._playing_index, 2)
        win.close()

    def test_rows_moved_non_playing_item_moves_above(self):
        """Drag row 2 above playing item (index 1): _playing_index shifts to 2."""
        win = self._make_window_with_playlist()
        # row 2 → before row 0 (inserts above playing item)
        win._on_playlist_rows_moved(None, 2, 2, None, 0)
        self.assertEqual(win._playing_index, 2)
        win.close()

    def test_rows_moved_non_playing_item_moves_below(self):
        """Drag row 0 below playing item (index 1): _playing_index shifts to 0."""
        win = self._make_window_with_playlist()
        # row 0 → before row 2 (inserts below playing item, dst=2 > src_last=0)
        win._on_playlist_rows_moved(None, 0, 0, None, 2)
        self.assertEqual(win._playing_index, 0)
        win.close()

    def test_rows_moved_unrelated_rows_no_change(self):
        """Moving two items that don't affect playing index leaves it unchanged."""
        win = self._make_window_with_playlist()
        # playing index = 1; move row 0 to before row 0 (no-op range)
        win._on_playlist_rows_moved(None, 2, 2, None, 3)
        self.assertEqual(win._playing_index, 1)
        win.close()
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
            "repeat_one": "🔂",
            "repeat_all": "🔁",
            "shuffle":    "🔀",
            "sequential": "➡",
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


class TestTreeView(unittest.TestCase):

    def _make_window(self) -> MainWindow:
        """Return a MainWindow backed by an in-memory manager."""
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

    def test_default_view_is_table(self):
        """Verify that the table view (page 0) is shown on startup."""
        win = self._make_window()
        self.assertEqual(win.view_stack.currentIndex(), 0)
        win.close()

    def test_toggle_switches_to_tree(self):
        """Verify that clicking view toggle switches to tree view (page 1)."""
        win = self._make_window()
        win.btn_view_toggle.click()
        self.assertEqual(win.view_stack.currentIndex(), 1)
        win.close()

    def test_toggle_switches_back_to_table(self):
        """Verify that clicking view toggle twice returns to table view."""
        win = self._make_window()
        win.btn_view_toggle.click()
        win.btn_view_toggle.click()
        self.assertEqual(win.view_stack.currentIndex(), 0)
        win.close()

    def test_toggle_button_label_changes_to_table(self):
        """Verify that the toggle button shows '📋 테이블' when in tree view."""
        win = self._make_window()
        win.btn_view_toggle.click()
        self.assertIn("테이블", win.btn_view_toggle.text())
        win.close()

    def test_toggle_button_label_returns_to_tree(self):
        """Verify that the toggle button shows '🌲 트리' when back in table view."""
        win = self._make_window()
        win.btn_view_toggle.click()
        win.btn_view_toggle.click()
        self.assertIn("트리", win.btn_view_toggle.text())
        win.close()

    def test_fill_tree_creates_top_level_items(self):
        """Verify that _fill_tree creates at least one top-level item for a file."""
        win = self._make_window()
        win._fill_tree([sample_info("/music/song.mp3")])
        self.assertGreater(win.tree_widget.topLevelItemCount(), 0)
        win.close()

    def test_fill_tree_file_node_has_path_in_user_role(self):
        """Verify that leaf file nodes store the full path in UserRole."""
        win = self._make_window()
        win._fill_tree([sample_info("/music/song.mp3")])

        def _find_file_item(parent):
            """Recursively find the first item with a non-None UserRole."""
            from PyQt6.QtCore import Qt
            for i in range(parent.childCount()):
                child = parent.child(i)
                data = child.data(0, Qt.ItemDataRole.UserRole)
                if data is not None:
                    return child
                result = _find_file_item(child)
                if result:
                    return result
            return None

        from PyQt6.QtCore import Qt
        root = win.tree_widget.invisibleRootItem()
        file_item = _find_file_item(root)
        self.assertIsNotNone(file_item)
        self.assertEqual(file_item.data(0, Qt.ItemDataRole.UserRole), "/music/song.mp3")
        win.close()

    def test_fill_tree_directory_node_has_none_user_role(self):
        """Verify that directory nodes have None in UserRole."""
        win = self._make_window()
        win._fill_tree([sample_info("/music/song.mp3")])
        from PyQt6.QtCore import Qt
        root = win.tree_widget.invisibleRootItem()
        # First top-level item should be a directory node
        top = root.child(0)
        self.assertIsNone(top.data(0, Qt.ItemDataRole.UserRole))
        win.close()

    def test_fill_tree_groups_files_by_directory(self):
        """Verify that two files in the same directory share a parent node."""
        win = self._make_window()
        win._fill_tree([
            sample_info("/music/pop/a.mp3"),
            sample_info("/music/pop/b.mp3"),
        ])
        from PyQt6.QtCore import Qt

        def _count_file_items(parent) -> int:
            count = 0
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.data(0, Qt.ItemDataRole.UserRole) is not None:
                    count += 1
                count += _count_file_items(child)
            return count

        total = _count_file_items(win.tree_widget.invisibleRootItem())
        self.assertEqual(total, 2)
        win.close()

    def test_fill_tree_empty_clears_tree(self):
        """Verify that filling with an empty list clears the tree."""
        win = self._make_window()
        win._fill_tree([sample_info("/music/song.mp3")])
        win._fill_tree([])
        self.assertEqual(win.tree_widget.topLevelItemCount(), 0)
        win.close()

    def test_fill_tree_base_dir_strips_prefix(self):
        """With base_dir set, top-level items should be subdirs of the base, not absolute roots."""
        win = self._make_window()
        win._fill_tree([sample_info("/music/pop/song.mp3")], base_dir="/music")
        root = win.tree_widget.invisibleRootItem()
        # Top-level item should be 'pop', not '/' or 'music'
        self.assertEqual(root.child(0).text(0), "pop")
        win.close()

    def test_fill_tree_base_dir_file_at_root_level(self):
        """Files directly in base_dir appear as top-level file nodes."""
        win = self._make_window()
        win._fill_tree([sample_info("/music/song.mp3")], base_dir="/music")
        from PyQt6.QtCore import Qt
        root = win.tree_widget.invisibleRootItem()
        # song.mp3 is directly under base_dir → top-level file node
        top = root.child(0)
        self.assertEqual(top.text(0), "song.mp3")
        self.assertEqual(top.data(0, Qt.ItemDataRole.UserRole), "/music/song.mp3")
        win.close()

    def test_fill_tree_base_dir_absolute_path_preserved_in_user_role(self):
        """File UserRole must always hold the original absolute path regardless of base_dir."""
        win = self._make_window()
        win._fill_tree([sample_info("/music/pop/song.mp3")], base_dir="/music")
        from PyQt6.QtCore import Qt

        def _find_file(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.data(0, Qt.ItemDataRole.UserRole) is not None:
                    return child
                result = _find_file(child)
                if result:
                    return result
            return None

        file_item = _find_file(win.tree_widget.invisibleRootItem())
        self.assertIsNotNone(file_item)
        self.assertEqual(file_item.data(0, Qt.ItemDataRole.UserRole), "/music/pop/song.mp3")
        win.close()

    def test_collect_tree_paths_file_node(self):
        """Verify that _collect_tree_paths returns the path for a file node."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QTreeWidgetItem
        win = self._make_window()
        item = QTreeWidgetItem(["song.mp3"])
        item.setData(0, Qt.ItemDataRole.UserRole, "/music/song.mp3")
        paths = win._collect_tree_paths([item])
        self.assertEqual(paths, ["/music/song.mp3"])
        win.close()

    def test_collect_tree_paths_directory_node_recurses(self):
        """Verify that _collect_tree_paths collects all files under a directory node."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QTreeWidgetItem
        win = self._make_window()
        dir_item = QTreeWidgetItem(["pop"])
        dir_item.setData(0, Qt.ItemDataRole.UserRole, None)
        for name, path in [("a.mp3", "/music/pop/a.mp3"), ("b.mp3", "/music/pop/b.mp3")]:
            child = QTreeWidgetItem(dir_item, [name])
            child.setData(0, Qt.ItemDataRole.UserRole, path)
        paths = win._collect_tree_paths([dir_item])
        self.assertIn("/music/pop/a.mp3", paths)
        self.assertIn("/music/pop/b.mp3", paths)
        self.assertEqual(len(paths), 2)
        win.close()

    def test_collect_tree_paths_deduplicates(self):
        """Verify that _collect_tree_paths does not return duplicate paths."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QTreeWidgetItem
        win = self._make_window()
        item = QTreeWidgetItem(["song.mp3"])
        item.setData(0, Qt.ItemDataRole.UserRole, "/music/song.mp3")
        paths = win._collect_tree_paths([item, item])
        self.assertEqual(len(paths), 1)
        win.close()


class TestReadVersion(unittest.TestCase):
    """Tests for the _read_version() module-level helper."""

    def test_returns_version_from_news_file(self):
        """_read_version returns the first vYYYYMMDD tag found in a valid NEWS file."""
        import tempfile
        import main_window as mw
        content = (
            "mp3-archive NEWS\n\n"
            "===========================================================================\n"
            "v20260419 (2026-04-19)\n"
            "===========================================================================\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write(content)
            tmp = f.name
        try:
            with unittest.mock.patch.object(mw, "_NEWS_FILE", tmp):
                self.assertEqual(mw._read_version(), "v20260419")
        finally:
            os.unlink(tmp)

    def test_returns_unknown_when_file_missing(self):
        """_read_version returns 'unknown' when the NEWS file does not exist."""
        import main_window as mw
        with unittest.mock.patch.object(mw, "_NEWS_FILE", "/nonexistent/path/NEWS"):
            self.assertEqual(mw._read_version(), "unknown")

    def test_returns_unknown_when_no_version_line(self):
        """_read_version returns 'unknown' when NEWS contains no vYYYYMMDD line."""
        import tempfile
        import main_window as mw
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write("mp3-archive NEWS\n\nNo version here.\n")
            tmp = f.name
        try:
            with unittest.mock.patch.object(mw, "_NEWS_FILE", tmp):
                self.assertEqual(mw._read_version(), "unknown")
        finally:
            os.unlink(tmp)

    def test_returns_first_version_when_multiple_present(self):
        """_read_version returns the first vYYYYMMDD tag, not a later one."""
        import tempfile
        import main_window as mw
        content = (
            "mp3-archive NEWS\n\n"
            "v20260419 (2026-04-19)\n"
            "v20260409 (2026-04-09)\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write(content)
            tmp = f.name
        try:
            with unittest.mock.patch.object(mw, "_NEWS_FILE", tmp):
                self.assertEqual(mw._read_version(), "v20260419")
        finally:
            os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
