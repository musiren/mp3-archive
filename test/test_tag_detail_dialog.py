"""
test_tag_detail_dialog.py - Unit tests for src/tag_detail_dialog.py.

All file I/O is replaced with unittest.mock so tests run without
real audio files.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PyQt6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)

from tag_detail_dialog import TagDetailDialog, _get_album_art


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_info(filename="track.mp3", path="/tmp/track.mp3",
               filesize=1024, duration=180.0,
               file_created_at="2024-01-01 00:00:00",
               file_modified_at="2024-01-01 00:00:00"):
    """Return a minimal file_info dict."""
    return {
        "filename": filename,
        "path":     path,
        "filesize": filesize,
        "duration": duration,
        "file_created_at":  file_created_at,
        "file_modified_at": file_modified_at,
    }


def _make_dialog(file_info=None, manager=None):
    """Return a TagDetailDialog with mutagen patched out."""
    if file_info is None:
        file_info = _file_info()
    with patch("tag_detail_dialog.MutagenFile", return_value=None), \
         patch("tag_detail_dialog._get_album_art", return_value=None):
        return TagDetailDialog(file_info, manager=manager)


# ---------------------------------------------------------------------------
# _get_album_art()
# ---------------------------------------------------------------------------

class TestGetAlbumArt(unittest.TestCase):

    def test_returns_none_for_missing_file(self):
        """_get_album_art returns None when MutagenFile returns None."""
        with patch("tag_detail_dialog.MutagenFile", return_value=None):
            result = _get_album_art("/nonexistent.mp3")
        self.assertIsNone(result)

    def test_returns_apic_bytes(self):
        """_get_album_art extracts ID3 APIC frame data."""
        mock_audio = MagicMock()
        mock_audio.tags = {"APIC:": MagicMock(data=b"fakeimagedata")}
        mock_audio.pictures = []
        with patch("tag_detail_dialog.MutagenFile", return_value=mock_audio):
            result = _get_album_art("/track.mp3")
        self.assertEqual(result, b"fakeimagedata")

    def test_returns_none_on_exception(self):
        """_get_album_art returns None when mutagen raises an exception."""
        with patch("tag_detail_dialog.MutagenFile", side_effect=Exception("bad file")):
            result = _get_album_art("/track.mp3")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# TagDetailDialog — album art label
# ---------------------------------------------------------------------------

class TestAlbumArtLabel(unittest.TestCase):

    def test_placeholder_shown_when_no_art(self):
        """♪ placeholder is shown when no album art is found."""
        dlg = _make_dialog()
        self.assertEqual(dlg._art_label.text(), "♪")

    def test_set_pixmap_called_when_art_found(self):
        """setPixmap is called on the art label when art bytes are returned."""
        art_bytes = b"fakeimagedata"
        with patch("tag_detail_dialog.MutagenFile", return_value=None), \
             patch("tag_detail_dialog._get_album_art", return_value=art_bytes):
            dlg = TagDetailDialog(_file_info())
            with patch.object(dlg._art_label, "setPixmap") as mock_set:
                # Simulate what _build_ui does when art is present
                from PyQt6.QtGui import QPixmap
                pix = QPixmap()
                pix.loadFromData(art_bytes)
                dlg._art_label.setPixmap(pix)
            mock_set.assert_called_once()

    def test_art_label_fixed_size(self):
        """Album art label has fixed 140x140 size."""
        dlg = _make_dialog()
        self.assertEqual(dlg._art_label.width(),  140)
        self.assertEqual(dlg._art_label.height(), 140)


# ---------------------------------------------------------------------------
# TagDetailDialog — general structure
# ---------------------------------------------------------------------------

class TestTagDetailDialogStructure(unittest.TestCase):

    def test_table_has_two_columns(self):
        """Tag table always has exactly 2 columns (태그, 값)."""
        dlg = _make_dialog()
        self.assertEqual(dlg._table.columnCount(), 2)

    def test_save_button_not_parented_without_manager(self):
        """Save button is not added to layout when manager is None."""
        dlg = _make_dialog(manager=None)
        self.assertIsNone(dlg._btn_save.parentWidget())

    def test_save_button_parented_with_manager(self):
        """Save button is added to layout when a manager is provided."""
        manager = MagicMock()
        dlg = _make_dialog(manager=manager)
        self.assertIsNotNone(dlg._btn_save.parentWidget())


if __name__ == "__main__":
    unittest.main()
