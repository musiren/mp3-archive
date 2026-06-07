"""
test_main_window_android.py - Tests for the Android Kivy UI.

All tests are skipped when kivy is not installed.
Full widget-level tests require a Kivy-capable environment (device or CI).
"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Suppress Kivy console output and avoid X display errors during import.
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")
os.environ.setdefault("DISPLAY", ":0")

try:
    import kivy  # noqa: F401
    _KIVY_OK = True
except Exception:
    _KIVY_OK = False


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestAppDirectory(unittest.TestCase):
    """Tests for Mp3ArchiveApp._storage_directory static method."""

    def test_fallback_to_cwd(self):
        """Verifies _storage_directory() returns cwd when android.storage is unavailable."""
        from main_window_android import Mp3ArchiveApp
        result = Mp3ArchiveApp._storage_directory()
        self.assertEqual(result, os.getcwd())

    def test_uses_android_storage_path(self):
        """Verifies _storage_directory() calls app_storage_path() when android.storage is present."""
        fake_android = types.ModuleType("android")
        fake_storage = types.ModuleType("android.storage")
        expected = "/data/user/0/org.musiren.mp3archive/files"
        fake_storage.app_storage_path = lambda: expected
        sys.modules.setdefault("android", fake_android)
        sys.modules["android.storage"] = fake_storage
        try:
            from main_window_android import Mp3ArchiveApp
            result = Mp3ArchiveApp._storage_directory()
            self.assertEqual(result, expected)
        finally:
            sys.modules.pop("android", None)
            sys.modules.pop("android.storage", None)

    def test_no_app_directory_name_collision(self):
        """Verifies the helper is not named _app_directory (Kivy App reserves it)."""
        from main_window_android import Mp3ArchiveApp
        self.assertIn("_storage_directory", Mp3ArchiveApp.__dict__)
        self.assertNotIn("_app_directory", Mp3ArchiveApp.__dict__)


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestKvLayout(unittest.TestCase):
    """Tests for the KivyMD KV layout string."""

    def test_kv_indentation_multiple_of_four(self):
        """Verifies every KV line is indented a multiple of 4 spaces (Kivy requirement)."""
        from main_window_android import KV
        for lineno, line in enumerate(KV.splitlines(), 1):
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip(" "))
            self.assertEqual(
                indent % 4, 0,
                f"KV line {lineno} indent={indent} not a multiple of 4: {line!r}",
            )

    def test_kv_root_is_not_bare_screen(self):
        """Verifies the KV root is not a bare ``Screen:`` (must be inside a ScreenManager).

        A standalone ``Screen`` widget renders an invisible UI on Android because its
        ``layout_children`` override (intended for ScreenManager transitions) overrides
        children's positions and its ``transition_state`` defaults to ``'out'``.
        """
        from main_window_android import KV
        toplevel = [
            line for line in KV.splitlines()
            if line and not line.startswith(" ") and line.rstrip().endswith(":")
        ]
        for line in toplevel:
            self.assertNotEqual(
                line.rstrip(), "Screen:",
                "KV root must not be a bare Screen — use MDBoxLayout (or a "
                "ScreenManager wrapper) to avoid the invisible-UI bug on Android.",
            )

    def test_kv_load_string_yields_expected_ids(self):
        """Verifies Builder.load_string(KV) exposes both the list and player tab ids."""
        from kivy.lang import Builder
        from main_window_android import KV
        root = Builder.load_string(KV)
        self.assertIsNotNone(root, "Builder.load_string returned None — KV has no root widget")
        expected = (
            "toolbar", "bottom_nav",
            "search_field", "chk_tags", "count_label",           # 목록 search
            "progress_bar", "status_label", "mp3_list", "mp3_grid",  # 목록 tab
            "mp3_table", "table_header", "table_rv", "table_rv_layout",  # 표 view
            "now_playing", "position_bar", "play_button",        # 재생 tab
        )
        for ident in expected:
            self.assertIn(ident, root.ids, f"KV id '{ident}' missing from root.ids")


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestKoreanFont(unittest.TestCase):
    """Tests for Korean font selection (fixes Hangul tofu boxes)."""

    def test_returns_first_existing_candidate(self):
        """Verifies _find_korean_font returns the first path the exists-predicate accepts."""
        from main_window_android import Mp3ArchiveApp, _KOREAN_FONT_CANDIDATES
        target = _KOREAN_FONT_CANDIDATES[1]
        font = Mp3ArchiveApp._find_korean_font(exists=lambda p: p == target)
        self.assertEqual(font, target)

    def test_returns_none_when_no_candidate_exists(self):
        """Verifies _find_korean_font returns None when no candidate font is present."""
        from main_window_android import Mp3ArchiveApp
        self.assertIsNone(Mp3ArchiveApp._find_korean_font(exists=lambda p: False))


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestScanSummary(unittest.TestCase):
    """Tests for the scan-result status message (fixes raw-tuple display)."""

    def test_includes_all_three_counts(self):
        """Verifies _format_scan_summary reports processed, skipped, and removed counts."""
        from main_window_android import Mp3ArchiveApp
        msg = Mp3ArchiveApp._format_scan_summary(3, 5, 2)
        self.assertIn("3", msg)
        self.assertIn("5", msg)
        self.assertIn("2", msg)

    def test_does_not_render_raw_tuple(self):
        """Verifies _format_scan_summary never embeds a raw tuple like '(3, 5, 2)'."""
        from main_window_android import Mp3ArchiveApp
        msg = Mp3ArchiveApp._format_scan_summary(3, 5, 2)
        self.assertNotIn("(3, 5, 2)", msg)


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestPermissions(unittest.TestCase):
    """Tests for runtime permission requests."""

    def test_no_raise_when_android_absent(self):
        """Verifies _request_android_permissions is a no-op (no exception) off-device."""
        from main_window_android import Mp3ArchiveApp
        Mp3ArchiveApp._request_android_permissions()  # must not raise


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestTimeFormat(unittest.TestCase):
    """Tests for the player's m:ss time formatter."""

    def test_formats_minutes_and_seconds(self):
        """Verifies _format_time renders minutes and zero-padded seconds."""
        from main_window_android import Mp3ArchiveApp
        self.assertEqual(Mp3ArchiveApp._format_time(0), "0:00")
        self.assertEqual(Mp3ArchiveApp._format_time(5), "0:05")
        self.assertEqual(Mp3ArchiveApp._format_time(95), "1:35")
        self.assertEqual(Mp3ArchiveApp._format_time(600), "10:00")

    def test_handles_none_and_negative(self):
        """Verifies _format_time treats None and negative values as 0:00."""
        from main_window_android import Mp3ArchiveApp
        self.assertEqual(Mp3ArchiveApp._format_time(None), "0:00")
        self.assertEqual(Mp3ArchiveApp._format_time(-3), "0:00")

    def test_truncates_fractional_seconds(self):
        """Verifies _format_time truncates fractional seconds (get_pos returns float)."""
        from main_window_android import Mp3ArchiveApp
        self.assertEqual(Mp3ArchiveApp._format_time(95.9), "1:35")


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestCountLabel(unittest.TestCase):
    """Tests for the 목록-tab song-count label text."""

    def test_full_count_when_no_keyword(self):
        """Verifies _count_label_text shows the total count when not searching."""
        from main_window_android import Mp3ArchiveApp
        self.assertEqual(Mp3ArchiveApp._count_label_text(5, ""), "전체 5곡")

    def test_search_count_when_keyword(self):
        """Verifies _count_label_text shows a search-result count when searching."""
        from main_window_android import Mp3ArchiveApp
        self.assertEqual(Mp3ArchiveApp._count_label_text(3, "abc"), "검색 결과: 3곡")


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestDialogContent(unittest.TestCase):
    """Tests for the metadata-dialog content widgets (자세히 / 가사)."""

    def test_tag_edit_content_exposes_fields(self):
        """Verifies TagEditContent provides the editable tag fields and info label."""
        from kivy.lang import Builder
        from main_window_android import KV, TagEditContent
        Builder.load_string(KV)  # register the <TagEditContent> rule
        content = TagEditContent()
        for fid in ("art_image", "tag_info", "f_title", "f_artist", "f_album",
                    "f_genre", "f_year", "f_comment"):
            self.assertIn(fid, content.ids, f"TagEditContent missing field '{fid}'")

    def test_lyrics_content_exposes_label(self):
        """Verifies LyricsContent provides the scrollable lyrics label id."""
        from kivy.lang import Builder
        from main_window_android import KV, LyricsContent
        Builder.load_string(KV)
        content = LyricsContent()
        self.assertIn("lyrics_label", content.ids)

    def test_song_info_content_exposes_ids(self):
        """Verifies SongInfoContent exposes header, search, status, results, and detail ids."""
        from kivy.lang import Builder
        from main_window_android import KV, SongInfoContent
        Builder.load_string(KV)
        content = SongInfoContent()
        for cid in ("si_header", "si_keyword", "si_source_btn", "si_progress",
                    "si_status", "si_results", "si_detail"):
            self.assertIn(cid, content.ids, f"SongInfoContent missing id '{cid}'")


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestSongDetailText(unittest.TestCase):
    """Tests for the 온라인 정보 dialog's per-candidate detail-text formatter."""

    def test_returns_empty_for_no_selection(self):
        """Verifies _song_detail_text returns '' when no candidate is selected."""
        from main_window_android import Mp3ArchiveApp
        self.assertEqual(Mp3ArchiveApp._song_detail_text(None), "")

    def test_includes_album_year_length_and_disambiguation(self):
        """Verifies the detail block lists chosen album, year, length, and qualifier."""
        from main_window_android import Mp3ArchiveApp
        cand = {
            "title": "Bohemian Rhapsody",
            "artist": "Queen",
            "album": "A Night at the Opera",
            "year": "1975",
            "length": "5:55",
            "disambiguation": "live",
            "releases": [],
        }
        text = Mp3ArchiveApp._song_detail_text(cand)
        self.assertIn("A Night at the Opera", text)
        self.assertIn("1975", text)
        self.assertIn("5:55", text)
        self.assertIn("live", text)

    def test_diff_marks_changed_fields_with_arrow(self):
        """Verifies a field whose value differs is shown as 'current → new'."""
        from main_window_android import Mp3ArchiveApp
        cand = {"title": "New Title", "artist": "Queen", "album": "Album"}
        current = {"title": "Old Title", "artist": "Queen", "album": "Album"}
        text = Mp3ArchiveApp._song_detail_text(cand, current)
        # Title changed -> arrow with both values.
        self.assertIn("Old Title → New Title", text)
        # Artist unchanged -> marked 동일, no arrow for that field.
        self.assertIn("아티스트: Queen (동일)", text)

    def test_diff_marks_empty_candidate_field_as_kept(self):
        """Verifies a blank candidate field is reported as '(유지)' (untouched)."""
        from main_window_android import Mp3ArchiveApp
        cand = {"title": "T", "artist": "", "album": "A"}
        current = {"title": "T0", "artist": "Existing Artist", "album": "A0"}
        text = Mp3ArchiveApp._song_detail_text(cand, current)
        self.assertIn("아티스트: Existing Artist (유지)", text)

    def test_diff_reports_no_change_when_all_identical(self):
        """Verifies the diff says nothing changes when every field already matches."""
        from main_window_android import Mp3ArchiveApp
        cand = {"title": "T", "artist": "A", "album": "B"}
        current = {"title": "T", "artist": "A", "album": "B"}
        text = Mp3ArchiveApp._song_detail_text(cand, current)
        self.assertIn("바뀌는 태그가 없습니다", text)

    def test_diff_shows_blank_current_as_dash(self):
        """Verifies an absent current value renders as '-' on the left of the arrow."""
        from main_window_android import Mp3ArchiveApp
        cand = {"title": "Fresh Title", "artist": "", "album": ""}
        text = Mp3ArchiveApp._song_detail_text(cand, {})
        self.assertIn("제목: - → Fresh Title", text)

    def test_lists_alternate_releases(self):
        """Verifies releases other than the chosen album appear under '다른 앨범'."""
        from main_window_android import Mp3ArchiveApp
        cand = {
            "album": "Studio",
            "year": "1975",
            "length": "5:55",
            "disambiguation": "",
            "releases": [
                {"title": "Studio", "year": "1975", "type": "Album"},
                {"title": "Greatest Hits", "year": "1981", "type": "Compilation"},
                {"title": "Live Tour", "year": "1992", "type": "Live"},
            ],
        }
        text = Mp3ArchiveApp._song_detail_text(cand)
        self.assertIn("다른 앨범", text)
        self.assertIn("Greatest Hits", text)
        self.assertIn("Compilation", text)
        self.assertIn("Live Tour", text)
        # The chosen album must not be re-listed under alternates.
        self.assertEqual(text.count("Studio"), 1)

    def test_truncates_long_alternate_release_list(self):
        """Verifies a long alternates list is capped with a '그 외 N개' tail line."""
        from main_window_android import Mp3ArchiveApp
        alternates = [
            {"title": f"Comp {i}", "year": "2000", "type": "Compilation"}
            for i in range(10)
        ]
        cand = {
            "album": "Studio",
            "year": "1975",
            "length": "5:55",
            "disambiguation": "",
            "releases": [{"title": "Studio", "year": "1975", "type": "Album"}] + alternates,
        }
        text = Mp3ArchiveApp._song_detail_text(cand)
        self.assertIn("그 외 4개", text)  # 10 alternates - 6 shown = 4

    def test_handles_missing_fields_gracefully(self):
        """Verifies missing length/disambiguation/releases do not raise."""
        from main_window_android import Mp3ArchiveApp
        text = Mp3ArchiveApp._song_detail_text({"album": "X", "year": "2020"})
        self.assertIn("X", text)


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestSearchDebounce(unittest.TestCase):
    """Tests that live search is debounced (Hangul IME fires on_text per jamo)."""

    def test_on_search_text_debounces(self):
        """Verifies on_search_text tracks the keyword and schedules a single timer."""
        import tempfile
        from main_window_android import Mp3ArchiveApp
        cwd = os.getcwd()
        tmp = tempfile.mkdtemp()
        os.chdir(tmp)  # app opens its DB in cwd off-device; isolate it
        try:
            app = Mp3ArchiveApp()
            try:
                app.on_search_text("ㄱ")
                self.assertEqual(app._search_keyword, "ㄱ")
                first = app._search_event
                self.assertIsNotNone(first, "no debounce timer scheduled")

                app.on_search_text("강")  # next keystroke before the timer fires
                self.assertEqual(app._search_keyword, "강")
                self.assertIsNotNone(app._search_event)
                # The earlier timer must be cancelled, not left to also fire.
                self.assertFalse(getattr(first, "is_triggered", False))
            finally:
                if app._search_event is not None:
                    app._search_event.cancel()
                app._manager.close()
        finally:
            os.chdir(cwd)


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestStorageRoot(unittest.TestCase):
    """Tests for the file-manager start directory."""

    def test_prefers_emulated_path(self):
        """Verifies _storage_root returns /storage/emulated/0 when it exists."""
        from main_window_android import Mp3ArchiveApp
        root = Mp3ArchiveApp._storage_root(exists=lambda p: True)
        self.assertEqual(root, "/storage/emulated/0")

    def test_falls_back_to_sdcard(self):
        """Verifies _storage_root returns /sdcard when only /sdcard exists."""
        from main_window_android import Mp3ArchiveApp
        root = Mp3ArchiveApp._storage_root(exists=lambda p: p == "/sdcard")
        self.assertEqual(root, "/sdcard")

    def test_falls_back_to_home(self):
        """Verifies _storage_root returns the home dir when no android root exists."""
        import os as _os
        from main_window_android import Mp3ArchiveApp
        root = Mp3ArchiveApp._storage_root(exists=lambda p: False)
        self.assertEqual(root, _os.path.expanduser("~"))


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestAllFilesAccess(unittest.TestCase):
    """Tests for the 'All files access' helpers (no-ops off-device)."""

    def test_has_access_true_off_device(self):
        """Verifies _has_all_files_access returns True when jnius is unavailable."""
        from main_window_android import Mp3ArchiveApp
        self.assertTrue(Mp3ArchiveApp._has_all_files_access())

    def test_request_access_no_raise_off_device(self):
        """Verifies _request_all_files_access is a no-op (no exception) off-device."""
        from main_window_android import Mp3ArchiveApp
        Mp3ArchiveApp._request_all_files_access()  # must not raise


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestRecycleList(unittest.TestCase):
    """Tests that the MP3 list is a virtualized RecycleView (fast repopulate)."""

    def test_mp3_list_is_recycleview(self):
        """Verifies the mp3_list widget is a RecycleView, not an eager MDList."""
        from kivy.lang import Builder
        from kivy.uix.recycleview import RecycleView
        from main_window_android import KV
        root = Builder.load_string(KV)
        self.assertIsInstance(root.ids.mp3_list, RecycleView)

    def test_mp3row_is_recycle_viewclass(self):
        """Verifies the row viewclasses implement the RecycleView data-view hook."""
        from main_window_android import Mp3RowDetails, Mp3RowList, Mp3TreeRow
        self.assertTrue(hasattr(Mp3RowDetails, "refresh_view_attrs"))
        self.assertTrue(hasattr(Mp3RowList, "refresh_view_attrs"))
        self.assertTrue(hasattr(Mp3RowDetails, "art_source"))
        self.assertTrue(hasattr(Mp3TreeRow, "refresh_view_attrs"))
        self.assertTrue(hasattr(Mp3TreeRow, "is_dir"))
        # Tree file rows must open the actions menu on long-press.
        self.assertTrue(hasattr(Mp3TreeRow, "on_long_touch"))
        from main_window_android import Mp3Tile
        self.assertTrue(hasattr(Mp3Tile, "refresh_view_attrs"))
        self.assertTrue(hasattr(Mp3Tile, "art_source"))
        from main_window_android import CandidateRow
        self.assertTrue(hasattr(CandidateRow, "refresh_view_attrs"))
        self.assertTrue(hasattr(CandidateRow, "cand_title"))
        self.assertTrue(hasattr(CandidateRow, "selected"))


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestSnackbarShim(unittest.TestCase):
    """Tests for the Snackbar compatibility shim (KivyMD 1.2.0 removed text=)."""

    def test_stores_text(self):
        """Verifies the shim stores the message for open() to display."""
        from main_window_android import Snackbar
        self.assertEqual(Snackbar(text="저장됨")._text, "저장됨")


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestFontFamilies(unittest.TestCase):
    """Tests that the Korean font targets every KivyMD font family, not just Roboto."""

    def test_covers_medium_and_light_families(self):
        """Verifies H6/Button (RobotoMedium) and H1/H2 (RobotoLight) families are registered."""
        from main_window_android import Mp3ArchiveApp
        fams = Mp3ArchiveApp._KIVYMD_FONT_FAMILIES
        for name in ("Roboto", "RobotoLight", "RobotoMedium", "RobotoBlack"):
            self.assertIn(name, fams)


if __name__ == "__main__":
    unittest.main()
