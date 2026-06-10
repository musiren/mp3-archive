"""
test_audio_meta.py - Tests for the GUI-independent audio_meta helpers.

These run locally (no PyQt6 or Kivy needed); only mutagen is required.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from audio_meta import (  # noqa: E402
    STANDARD_EASY_KEYS, _clean_lyrics, fix_mojibake, format_summary_rows,
    get_album, get_album_art, get_lyrics, get_stream_info, read_all_tags,
    tag_display_label, to_easy_tags,
)


class TestTagDisplayLabel(unittest.TestCase):
    """Tests for tag_display_label() and the standard-key set."""

    def test_known_key_is_translated(self):
        """Verifies a known easy-tag key maps to its Korean label."""
        self.assertEqual(tag_display_label("albumartist"), "앨범 아티스트")
        self.assertEqual(tag_display_label("composer"), "작곡가")

    def test_unknown_key_returns_itself(self):
        """Verifies an unrecognised key is returned unchanged."""
        self.assertEqual(tag_display_label("mood"), "mood")

    def test_standard_keys_cover_the_six_form_fields(self):
        """Verifies the standard-key set matches the dialog's dedicated fields."""
        self.assertEqual(
            STANDARD_EASY_KEYS,
            {"title", "artist", "album", "genre", "date", "comment"},
        )


class TestReadAllTags(unittest.TestCase):
    """Tests for read_all_tags()."""

    def test_returns_empty_for_nonexistent_file(self):
        """Verifies read_all_tags returns [] for a missing path."""
        self.assertEqual(read_all_tags("/no/such/file.mp3"), [])

    def test_returns_empty_for_non_audio_file(self):
        """Verifies read_all_tags returns [] for a plain text file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not audio")
            path = f.name
        try:
            self.assertEqual(read_all_tags(path), [])
        finally:
            os.remove(path)


class TestGetStreamInfo(unittest.TestCase):
    """Tests for get_stream_info()."""

    def test_returns_empty_for_nonexistent_file(self):
        """Verifies get_stream_info returns {} for a missing path."""
        self.assertEqual(get_stream_info("/no/such/file.mp3"), {})

    def test_returns_empty_for_non_audio_file(self):
        """Verifies get_stream_info returns {} for a plain text file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not audio")
            path = f.name
        try:
            self.assertEqual(get_stream_info(path), {})
        finally:
            os.remove(path)


class TestFormatSummaryRows(unittest.TestCase):
    """Tests for format_summary_rows()."""

    def test_file_level_rows_always_present(self):
        """Verifies size/duration/created/modified rows are produced from the DB info."""
        info = {
            "filesize": 1536,
            "duration": 95,
            "file_created_at": "2026-01-01 10:00:00",
            "file_modified_at": "2026-02-02 11:00:00",
        }
        rows = dict(format_summary_rows(info))
        self.assertEqual(rows["크기"], "1.5 KB")
        self.assertEqual(rows["길이"], "1:35")
        self.assertEqual(rows["생성일시"], "2026-01-01 10:00:00")
        self.assertEqual(rows["수정일시"], "2026-02-02 11:00:00")

    def test_missing_fields_render_as_dash(self):
        """Verifies absent size/duration/timestamps degrade to '-'."""
        rows = dict(format_summary_rows({}))
        self.assertEqual(rows["크기"], "-")
        self.assertEqual(rows["길이"], "-")
        self.assertEqual(rows["생성일시"], "-")

    def test_stream_rows_included_when_present(self):
        """Verifies sample rate / channels / bitrate rows appear from stream info."""
        stream = {"sample_rate": 44100, "channels": 2, "bitrate": 320000}
        rows = dict(format_summary_rows({}, stream))
        self.assertEqual(rows["샘플레이트"], "44100 Hz")
        self.assertEqual(rows["채널"], "2")
        self.assertEqual(rows["비트레이트"], "320 kbps")

    def test_stream_rows_omitted_when_absent(self):
        """Verifies no stream rows are added when stream info is empty."""
        labels = [label for label, _ in format_summary_rows({}, {})]
        self.assertNotIn("샘플레이트", labels)
        self.assertNotIn("비트레이트", labels)

    def test_duration_falls_back_to_stream_length(self):
        """Verifies length is taken from stream info when the DB duration is absent."""
        rows = dict(format_summary_rows({}, {"length": 200.0}))
        self.assertEqual(rows["길이"], "3:20")

    def test_filesize_megabytes(self):
        """Verifies large sizes format as MB."""
        rows = dict(format_summary_rows({"filesize": 5 * 1024 * 1024}))
        self.assertEqual(rows["크기"], "5.0 MB")


class TestGetLyrics(unittest.TestCase):
    """Tests for get_lyrics()."""

    def test_returns_none_for_empty_path(self):
        """Verifies get_lyrics returns None for an empty path."""
        self.assertIsNone(get_lyrics(""))

    def test_returns_none_for_nonexistent_file(self):
        """Verifies get_lyrics returns None for a path that does not exist."""
        self.assertIsNone(get_lyrics("/no/such/file.mp3"))

    def test_returns_none_for_non_audio_file(self):
        """Verifies get_lyrics returns None for a plain text file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not audio")
            path = f.name
        try:
            self.assertIsNone(get_lyrics(path))
        finally:
            os.remove(path)


class TestGetAlbumArt(unittest.TestCase):
    """Tests for get_album_art()."""

    def test_returns_none_for_nonexistent_file(self):
        """Verifies get_album_art returns None for a missing file."""
        self.assertIsNone(get_album_art("/no/such/file.mp3"))

    def test_returns_none_for_non_audio_file(self):
        """Verifies get_album_art returns None for a plain text file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not audio")
            path = f.name
        try:
            self.assertIsNone(get_album_art(path))
        finally:
            os.remove(path)


class TestGetAlbum(unittest.TestCase):
    """Tests for get_album()."""

    def test_returns_none_for_empty_path(self):
        """Verifies get_album returns None for an empty path."""
        self.assertIsNone(get_album(""))

    def test_returns_none_for_nonexistent_file(self):
        """Verifies get_album returns None for a missing file."""
        self.assertIsNone(get_album("/no/such/file.mp3"))

    def test_returns_none_for_non_audio_file(self):
        """Verifies get_album returns None for a plain text file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not audio")
            path = f.name
        try:
            self.assertIsNone(get_album(path))
        finally:
            os.remove(path)


class TestToEasyTags(unittest.TestCase):
    """Tests for to_easy_tags() form-to-tag mapping."""

    def test_maps_year_to_date(self):
        """Verifies the 'year' form field maps to the easy-tag 'date' key."""
        tags = to_easy_tags({"year": "2020"})
        self.assertEqual(tags, {"date": "2020"})

    def test_drops_blank_values(self):
        """Verifies blank/whitespace fields are omitted so they don't clobber tags."""
        tags = to_easy_tags({"title": "Song", "artist": "", "album": "   "})
        self.assertEqual(tags, {"title": "Song"})

    def test_strips_and_maps_known_fields(self):
        """Verifies known fields are stripped and mapped to easy-tag keys."""
        tags = to_easy_tags({
            "title": " T ", "artist": "A", "album": "Al",
            "genre": "Pop", "comment": "c", "unknown": "x",
        })
        self.assertEqual(tags, {
            "title": "T", "artist": "A", "album": "Al",
            "genre": "Pop", "comment": "c",
        })


class TestCleanLyrics(unittest.TestCase):
    """Tests for lyrics line-ending normalization."""

    def test_normalizes_crlf_and_cr(self):
        """Verifies CRLF and bare CR line endings collapse to LF."""
        self.assertEqual(_clean_lyrics("line1\r\nline2\rline3"), "line1\nline2\nline3")

    def test_leaves_lf_unchanged(self):
        """Verifies plain LF text is returned unchanged."""
        self.assertEqual(_clean_lyrics("a\nb"), "a\nb")

    def test_handles_none_and_empty(self):
        """Verifies None and empty pass through untouched."""
        self.assertIsNone(_clean_lyrics(None))
        self.assertEqual(_clean_lyrics(""), "")


class TestFixMojibake(unittest.TestCase):
    """Tests for CP949/EUC-KR-as-Latin-1 mojibake repair."""

    def test_repairs_cp949_decoded_as_latin1(self):
        """Verifies Korean read as Latin-1 from CP949 bytes is restored."""
        original = "아주오래된연인들"
        mojibake = original.encode("cp949").decode("latin-1")
        self.assertEqual(fix_mojibake(mojibake), original)

    def test_leaves_correct_korean_unchanged(self):
        """Verifies already-correct Korean (Hangul) is returned unchanged."""
        self.assertEqual(fix_mojibake("내맘이야"), "내맘이야")

    def test_leaves_latin_text_unchanged(self):
        """Verifies genuine Latin titles are not falsely 'repaired'."""
        for s in ["Smells Like Teen Spirit", "015B", "TakeTwo", "Vlad"]:
            self.assertEqual(fix_mojibake(s), s)

    def test_handles_none_and_empty(self):
        """Verifies None and empty string pass through untouched."""
        self.assertIsNone(fix_mojibake(None))
        self.assertEqual(fix_mojibake(""), "")


if __name__ == "__main__":
    unittest.main()
