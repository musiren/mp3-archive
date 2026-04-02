"""
test_lyrics_dialog.py - Unit tests for src/lyrics_dialog.py.
"""

import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from lyrics_dialog import LyricsDialog, _get_lyrics

_app = QApplication.instance() or QApplication(sys.argv)


def _sample_info(**kwargs) -> dict:
    """Return a minimal file_info dict for dialog construction tests."""
    base = {
        "path": "/music/song.mp3",
        "filename": "song.mp3",
        "title": "Test Song",
        "artist": "Test Artist",
        "album": None,
        "genre": None,
        "year": None,
        "comment": None,
        "duration": 180.0,
        "filesize": 4096,
        "file_created_at": None,
        "file_modified_at": None,
    }
    base.update(kwargs)
    return base


class TestGetLyrics(unittest.TestCase):

    def test_returns_none_for_nonexistent_file(self):
        """Verify that _get_lyrics returns None for a path that does not exist."""
        result = _get_lyrics("/nonexistent/path/song.mp3")
        self.assertIsNone(result)

    def test_returns_none_for_empty_path(self):
        """Verify that _get_lyrics returns None when path is empty string."""
        result = _get_lyrics("")
        self.assertIsNone(result)

    def test_returns_none_for_non_audio_file(self):
        """Verify that _get_lyrics returns None for a plain text file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not an audio file")
            path = f.name
        try:
            result = _get_lyrics(path)
            self.assertIsNone(result)
        finally:
            os.unlink(path)

    def test_does_not_raise_on_corrupt_file(self):
        """Verify that _get_lyrics never raises, even for corrupt files."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"\x00" * 64)
            path = f.name
        try:
            try:
                _get_lyrics(path)
            except Exception as e:
                self.fail(f"_get_lyrics raised unexpectedly: {e}")
        finally:
            os.unlink(path)


class TestLyricsDialog(unittest.TestCase):

    def test_dialog_opens_without_error(self):
        """Verify that LyricsDialog can be constructed without raising."""
        try:
            dlg = LyricsDialog(_sample_info(), parent=None)
            dlg.close()
        except Exception as e:
            self.fail(f"LyricsDialog raised unexpectedly: {e}")

    def test_dialog_shows_no_lyrics_notice_when_file_missing(self):
        """Verify that the dialog shows a fallback notice for missing files."""
        dlg = LyricsDialog(_sample_info(path="/no/such/file.mp3"), parent=None)
        # Find the QTextEdit and check its content
        from PyQt6.QtWidgets import QTextEdit
        text_edit = dlg.findChild(QTextEdit)
        self.assertIsNotNone(text_edit)
        self.assertIn("가사 정보가 없습니다", text_edit.toPlainText())
        dlg.close()

    def test_dialog_title_and_artist_labels_present(self):
        """Verify that the dialog renders title and artist information."""
        dlg = LyricsDialog(_sample_info(title="My Song", artist="My Artist"), parent=None)
        from PyQt6.QtWidgets import QLabel
        texts = [w.text() for w in dlg.findChildren(QLabel)]
        combined = " ".join(texts)
        self.assertIn("My Song", combined)
        self.assertIn("My Artist", combined)
        dlg.close()

    def test_dialog_uses_filename_when_title_missing(self):
        """Verify that filename is used as fallback when title is None."""
        dlg = LyricsDialog(_sample_info(title=None, filename="track.mp3"), parent=None)
        from PyQt6.QtWidgets import QLabel
        texts = [w.text() for w in dlg.findChildren(QLabel)]
        combined = " ".join(texts)
        self.assertIn("track.mp3", combined)
        dlg.close()


if __name__ == "__main__":
    unittest.main()
