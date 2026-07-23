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
class TestRowInfosForPaths(unittest.TestCase):
    """Tests for the bulk queue-item lookup used by the add-to-queue paths."""

    def _stub_app(self, files):
        """Build a minimal stand-in exposing _files and the DB fallback."""
        from main_window_android import Mp3ArchiveApp
        stub = types.SimpleNamespace(_files=files)
        stub._row_info_for_path = (
            lambda path: Mp3ArchiveApp._row_info_for_path(stub, path))
        stub._manager = types.SimpleNamespace(get_by_path=lambda path: None)
        return stub

    def test_resolves_in_list_order(self):
        """Verifies paths in the list resolve to queue dicts, order preserved."""
        from main_window_android import Mp3ArchiveApp
        files = [{"path": f"/m/{i}.mp3", "filename": f"{i}.mp3",
                  "artist": f"a{i}", "title": f"t{i}"} for i in range(3)]
        infos = Mp3ArchiveApp._row_infos_for_paths(
            self._stub_app(files), [f["path"] for f in files])
        self.assertEqual([i["title"] for i in infos], ["t0", "t1", "t2"])
        self.assertEqual(infos[0],
                         {"path": "/m/0.mp3", "filename": "0.mp3",
                          "artist": "a0", "title": "t0"})

    def test_unknown_paths_dropped(self):
        """Verifies paths absent from the list and the DB are dropped."""
        from main_window_android import Mp3ArchiveApp
        files = [{"path": "/m/0.mp3", "filename": "0.mp3",
                  "artist": "a", "title": "t"}]
        infos = Mp3ArchiveApp._row_infos_for_paths(
            self._stub_app(files), ["/gone.mp3", "/m/0.mp3"])
        self.assertEqual(len(infos), 1)
        self.assertEqual(infos[0]["path"], "/m/0.mp3")

    def test_scales_linearly(self):
        """Verifies a 30k-path bulk lookup stays fast (single index pass)."""
        import time
        from main_window_android import Mp3ArchiveApp
        n = 30_000
        files = [{"path": f"/m/{i}.mp3", "filename": f"{i}.mp3",
                  "artist": "a", "title": "t"} for i in range(n)]
        start = time.perf_counter()
        infos = Mp3ArchiveApp._row_infos_for_paths(
            self._stub_app(files), [f["path"] for f in files])
        elapsed = time.perf_counter() - start
        self.assertEqual(len(infos), n)
        # The old per-path linear rescan took ~20s+ at this size; the indexed
        # pass is tens of milliseconds. 2s leaves headroom for slow machines.
        self.assertLess(elapsed, 2.0)


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
            "now_art", "volume_slider",                          # art + volume
            "queue_rv", "queue_count", "lower_toggle", "lyrics_view",  # 재생목록/가사
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

    def test_long_touch_duration_shortened(self):
        """Verifies every long-pressable row uses the 0.3 s long-touch threshold."""
        from main_window_android import (
            _LONG_TOUCH_SECONDS, Mp3RowDetails, Mp3RowList, Mp3TreeRow,
            Mp3Tile, QueueRow)
        self.assertEqual(_LONG_TOUCH_SECONDS, 0.3)
        # Read the class-level Property default (no instance: instantiating a
        # KivyMD widget needs a running MDApp).
        for cls in (Mp3RowDetails, Mp3RowList, Mp3TreeRow, Mp3Tile, QueueRow):
            self.assertEqual(cls.duration_long_touch.defaultvalue, 0.3,
                             cls.__name__)


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestSnackbarShim(unittest.TestCase):
    """Tests for the Snackbar compatibility shim (KivyMD 1.2.0 removed text=)."""

    def test_stores_text(self):
        """Verifies the shim stores the message for open() to display."""
        from main_window_android import Snackbar
        self.assertEqual(Snackbar(text="저장됨")._text, "저장됨")


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestSessionPersistence(unittest.TestCase):
    """Tests for the save-on-exit / restore-on-launch session helpers."""

    @staticmethod
    def _memory_manager():
        """Return an Mp3Manager backed by an in-memory SQLite database."""
        import sqlite3
        from mp3_manager import Mp3Manager, _create_table
        mgr = Mp3Manager.__new__(Mp3Manager)
        mgr._conn = sqlite3.connect(":memory:")
        _create_table(mgr._conn)
        return mgr

    def _stub_app(self, mgr, **overrides):
        """Build a minimal app stand-in carrying the persisted session state."""
        from main_window_android import Mp3ArchiveApp
        from playlist import PlayQueue
        stub = types.SimpleNamespace(
            _state=mgr, _manager=mgr, _db_path="",
            _shuffle_on=True, _repeat_mode="sequential", _shuffle_seed=777,
            _theme_choice="dark", _view_mode="table", _show_art=False,
            _queue_source=None, _queue=PlayQueue(), _playing_path="",
            _resume_index=-1, _resume_pos=0.0, _svc_pos=0.0,
            _sound=None, _elapsed=0.0, _paused_pos=0.0,
        )
        for key, value in overrides.items():
            setattr(stub, key, value)
        stub._effective_mode = "shuffle" if stub._shuffle_on else stub._repeat_mode
        stub._svc_active = lambda: False
        stub._current_position = (
            lambda: Mp3ArchiveApp._current_position(stub))
        stub._save_app_state = (
            lambda: Mp3ArchiveApp._save_app_state(stub))
        return stub

    def test_save_persists_prefs(self):
        """Verifies shuffle/repeat/seed/theme/view/art preferences reach the DB."""
        mgr = self._memory_manager()
        self._stub_app(mgr)._save_app_state()
        self.assertEqual(mgr.get_state("shuffle_on"), "1")
        self.assertEqual(mgr.get_state("repeat_mode"), "sequential")
        self.assertEqual(mgr.get_state("play_mode"), "shuffle")
        self.assertEqual(mgr.get_state("shuffle_seed"), "777")
        self.assertEqual(mgr.get_state("theme"), "dark")
        self.assertEqual(mgr.get_state("view_mode"), "table")
        self.assertEqual(mgr.get_state("show_art"), "0")
        mgr.close()

    def test_save_stores_queue_rows_without_source(self):
        """Verifies a hand-built queue persists its ordered paths."""
        mgr = self._memory_manager()
        stub = self._stub_app(mgr)
        stub._queue.add_many([{"path": "/m/b.mp3"}, {"path": "/m/a.mp3"}])
        stub._save_app_state()
        self.assertEqual(mgr.get_state("queue_source"), "")
        self.assertEqual(mgr.load_queue(), ["/m/b.mp3", "/m/a.mp3"])
        mgr.close()

    def test_save_stores_only_list_source(self):
        """Verifies a .list-mirrored queue persists just the file path."""
        mgr = self._memory_manager()
        stub = self._stub_app(mgr, _queue_source="/m/주말.list")
        stub._queue.add_many([{"path": "/m/a.mp3"}])
        stub._save_app_state()
        self.assertEqual(mgr.get_state("queue_source"), "/m/주말.list")
        self.assertEqual(mgr.load_queue(), [])   # the file is the source
        mgr.close()

    def test_save_records_paused_track_and_position(self):
        """Verifies the loaded track, queue index, and position are saved."""
        mgr = self._memory_manager()
        stub = self._stub_app(mgr, _playing_path="/m/a.mp3", _svc_pos=83.4)
        stub._svc_active = lambda: True
        stub._queue.add_many([{"path": "/m/x.mp3"}, {"path": "/m/a.mp3"}])
        stub._queue.set_current(1)
        stub._save_app_state()
        self.assertEqual(mgr.get_state("now_path"), "/m/a.mp3")
        self.assertEqual(mgr.get_state("now_index"), "1")
        self.assertEqual(mgr.get_state("now_pos"), "83.4")
        mgr.close()

    def test_save_keeps_unresumed_restore_target(self):
        """Verifies quitting again before pressing play keeps the saved spot."""
        mgr = self._memory_manager()
        stub = self._stub_app(mgr, _resume_index=0, _resume_pos=42.0)
        stub._queue.add_many([{"path": "/m/a.mp3"}])
        stub._save_app_state()
        self.assertEqual(mgr.get_state("now_path"), "/m/a.mp3")
        self.assertEqual(mgr.get_state("now_index"), "0")
        self.assertEqual(mgr.get_state("now_pos"), "42.0")
        mgr.close()

    def test_restore_pref_validates_values(self):
        """Verifies saved prefs are validated against the allowed set."""
        from main_window_android import Mp3ArchiveApp
        mgr = self._memory_manager()
        stub = types.SimpleNamespace(_state=mgr)
        mgr.set_state("view_mode", "tree")
        self.assertEqual(
            Mp3ArchiveApp._restore_pref(stub, "view_mode", "details",
                                        ("details", "tree")), "tree")
        mgr.set_state("view_mode", "bogus")
        self.assertEqual(
            Mp3ArchiveApp._restore_pref(stub, "view_mode", "details",
                                        ("details", "tree")), "details")
        self.assertEqual(
            Mp3ArchiveApp._restore_pref(stub, "unsaved", "fallback",
                                        ("fallback", "x")), "fallback")
        mgr.close()

    def test_restore_seed_round_trips(self):
        """Verifies the saved seed is reused; absence generates a fresh one."""
        from main_window_android import Mp3ArchiveApp
        mgr = self._memory_manager()
        stub = types.SimpleNamespace(_state=mgr)
        mgr.set_state("shuffle_seed", 12345)
        self.assertEqual(Mp3ArchiveApp._restore_seed(stub), 12345)
        mgr.set_state("shuffle_seed", None)
        self.assertGreater(Mp3ArchiveApp._restore_seed(stub), 0)
        mgr.close()

    def test_queue_changed_reseeds_and_clears_source(self):
        """Verifies any queue edit invalidates the seed and the .list source."""
        from main_window_android import Mp3ArchiveApp
        stub = types.SimpleNamespace(_shuffle_seed=777,
                                     _queue_source="/m/주말.list")
        Mp3ArchiveApp._queue_changed(stub)
        self.assertNotEqual(stub._shuffle_seed, 777)
        self.assertGreater(stub._shuffle_seed, 0)
        self.assertIsNone(stub._queue_source)

    def test_save_records_external_library_db(self):
        """Verifies the active external library DB path is saved for relaunch."""
        mgr = self._memory_manager()
        stub = self._stub_app(mgr, _manager=object(),
                              _db_path="/m/mp3_archive.db")
        stub._save_app_state()
        self.assertEqual(mgr.get_state("library_db"), "/m/mp3_archive.db")
        mgr.close()

    def test_save_clears_library_db_for_internal(self):
        """Verifies the pointer is emptied when the internal DB is the library."""
        mgr = self._memory_manager()
        self._stub_app(mgr)._save_app_state()
        self.assertEqual(mgr.get_state("library_db"), "")
        mgr.close()


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestLibraryDb(unittest.TestCase):
    """Tests for the per-directory library DB switching and restore."""

    def _stub_app(self, tmp):
        """Build a stand-in with a real state DB inside the *tmp* directory."""
        from main_window_android import Mp3ArchiveApp
        from mp3_manager import Mp3Manager
        stub = types.SimpleNamespace(
            _state_db_path=os.path.join(tmp, "state.db"), _last_dir=None)
        stub._state = Mp3Manager(stub._state_db_path)
        stub._manager = stub._state
        stub._db_path = stub._state_db_path
        stub._set_library_db = (
            lambda p: Mp3ArchiveApp._set_library_db(stub, p))
        return stub

    def test_set_library_db_switches_and_records(self):
        """Verifies switching to an external DB opens it and saves the pointer."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            stub = self._stub_app(tmp)
            ext = os.path.join(tmp, "music", "mp3_archive.db")
            os.makedirs(os.path.dirname(ext))
            stub._set_library_db(ext)
            self.assertIsNot(stub._manager, stub._state)
            self.assertEqual(stub._db_path, ext)
            self.assertEqual(stub._state.get_state("library_db"), ext)
            self.assertTrue(os.path.isfile(ext))
            stub._manager.close()
            stub._state.close()

    def test_set_library_db_back_to_internal(self):
        """Verifies pointing back at the internal DB reuses the state manager."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            stub = self._stub_app(tmp)
            ext = os.path.join(tmp, "mp3_archive.db")
            stub._set_library_db(ext)
            stub._set_library_db(stub._state_db_path)
            self.assertIs(stub._manager, stub._state)
            self.assertEqual(stub._state.get_state("library_db"), "")
            stub._state.close()

    def test_restore_reopens_saved_library_db(self):
        """Verifies the saved external DB is reopened with its scan directory."""
        import tempfile
        from main_window_android import Mp3ArchiveApp
        from mp3_manager import Mp3Manager
        with tempfile.TemporaryDirectory() as tmp:
            ext = os.path.join(tmp, "music", "mp3_archive.db")
            os.makedirs(os.path.dirname(ext))
            Mp3Manager(ext).close()   # the file the last session scanned into
            stub = self._stub_app(tmp)
            stub._state.set_state("library_db", ext)
            Mp3ArchiveApp._restore_library_db(stub)
            self.assertEqual(stub._db_path, ext)
            self.assertEqual(stub._last_dir, os.path.dirname(ext))
            stub._manager.close()
            stub._state.close()

    def test_restore_ignores_missing_or_unsaved_db(self):
        """Verifies launch keeps the internal DB when no saved DB exists."""
        import tempfile
        from main_window_android import Mp3ArchiveApp
        with tempfile.TemporaryDirectory() as tmp:
            stub = self._stub_app(tmp)
            Mp3ArchiveApp._restore_library_db(stub)   # never scanned
            self.assertIs(stub._manager, stub._state)
            stub._state.set_state("library_db", os.path.join(tmp, "gone.db"))
            Mp3ArchiveApp._restore_library_db(stub)   # file disappeared
            self.assertIs(stub._manager, stub._state)
            self.assertIsNone(stub._last_dir)
            stub._state.close()

    def _picker_stub(self):
        """Build a stand-in recording how a file-manager pick was routed."""
        calls = []
        stub = types.SimpleNamespace()
        stub._close_file_manager = lambda *a: None
        stub._load_database = lambda p: calls.append(("load", p))
        stub._scan_directory = lambda d: calls.append(("scan", d))
        return stub, calls

    def test_pick_routes_db_file_to_load(self):
        """Verifies picking a .db file loads it instead of scanning."""
        import tempfile
        from main_window_android import Mp3ArchiveApp
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "mp3_archive.db")
            open(db, "w").close()
            stub, calls = self._picker_stub()
            Mp3ArchiveApp._on_dir_selected(stub, db)
            self.assertEqual(calls, [("load", db)])

    def test_pick_routes_directory_to_scan(self):
        """Verifies picking a directory starts a scan as before."""
        import tempfile
        from main_window_android import Mp3ArchiveApp
        with tempfile.TemporaryDirectory() as tmp:
            stub, calls = self._picker_stub()
            Mp3ArchiveApp._on_dir_selected(stub, tmp)
            self.assertEqual(calls, [("scan", tmp)])

    def test_pick_rejects_other_files(self):
        """Verifies a non-.db file pick neither loads nor scans."""
        import tempfile
        from unittest import mock
        import main_window_android
        from main_window_android import Mp3ArchiveApp
        with tempfile.TemporaryDirectory() as tmp:
            other = os.path.join(tmp, "song.mp3")
            open(other, "w").close()
            stub, calls = self._picker_stub()
            with mock.patch.object(main_window_android, "Snackbar") as snack:
                Mp3ArchiveApp._on_dir_selected(stub, other)
            self.assertEqual(calls, [])
            snack.assert_called_once()

    def test_scan_directory_uses_per_directory_db(self):
        """Verifies a picked folder scans into <folder>/mp3_archive.db."""
        from main_window_android import LIBRARY_DB_NAME, Mp3ArchiveApp
        calls = []
        stub = types.SimpleNamespace(_state_db_path="/internal/state.db")
        stub._set_library_db = lambda p: calls.append(("db", p))
        stub._start_scan = (
            lambda d, force=False, replace=False:
            calls.append(("scan", d, replace)))
        Mp3ArchiveApp._scan_directory(stub, "/music")
        self.assertEqual(calls, [
            ("db", os.path.join("/music", LIBRARY_DB_NAME)),
            ("scan", "/music", False),
        ])

    def test_scan_directory_falls_back_to_internal_db(self):
        """Verifies an unwritable folder scans into the internal DB, replacing."""
        from main_window_android import Mp3ArchiveApp
        calls = []
        stub = types.SimpleNamespace(_state_db_path="/internal/state.db")

        def set_db(path):
            """Reject any DB outside the internal one, like a read-only dir."""
            if path != "/internal/state.db":
                raise OSError("unable to open database file")
            calls.append(("db", path))

        stub._set_library_db = set_db
        stub._start_scan = (
            lambda d, force=False, replace=False:
            calls.append(("scan", d, replace)))
        Mp3ArchiveApp._scan_directory(stub, "/readonly")
        self.assertEqual(calls, [
            ("db", "/internal/state.db"),
            ("scan", "/readonly", True),
        ])


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestQueueTagDetail(unittest.TestCase):
    """Tests for the 재생목록 long-press 자세히 (tag detail) action."""

    def test_show_tag_detail_ignores_empty_path(self):
        """Verifies a queue item without a path opens nothing (no crash)."""
        from main_window_android import Mp3ArchiveApp
        stub = types.SimpleNamespace()   # any attribute access would raise
        self.assertIsNone(Mp3ArchiveApp._show_tag_detail(stub, ""))

    def test_open_detail_delegates_to_show_tag_detail(self):
        """Verifies the list-row 자세히 action reuses the shared dialog body."""
        from main_window_android import Mp3ArchiveApp
        calls = []
        stub = types.SimpleNamespace(
            _actions_dialog=types.SimpleNamespace(dismiss=lambda: None))
        stub._show_tag_detail = lambda p: calls.append(p)
        row = types.SimpleNamespace(path="/m/a.mp3")
        Mp3ArchiveApp._open_detail(stub, row)
        self.assertEqual(calls, ["/m/a.mp3"])

    def test_queue_actions_include_tag_detail(self):
        """Verifies the queue long-press menu wires a 자세히 action."""
        import inspect
        from main_window_android import Mp3ArchiveApp
        source = inspect.getsource(Mp3ArchiveApp.open_queue_actions)
        self.assertIn("자세히", source)
        self.assertIn("_show_tag_detail", source)


@unittest.skipUnless(_KIVY_OK, "kivy not installed — android UI tests skipped")
class TestTreeSelection(unittest.TestCase):
    """Tests for the lazily-indexed 트리 view selection paths."""

    def _stub_app(self):
        """Build a minimal app stand-in exposing the tree selection state."""
        from main_window_android import Mp3ArchiveApp
        stub = types.SimpleNamespace(
            _files=[{"path": p} for p in
                    ("/m/A/1.mp3", "/m/A/2.mp3", "/m/B/3.mp3")],
            _last_dir="/m", _tree_index=None, _expanded=set(),
            _selected=set(), _sort_mode="artist", selection_count=0,
            _refreshed_at=[],
        )
        stub._get_tree_index = (
            lambda: Mp3ArchiveApp._get_tree_index(stub))
        stub._tree_rows = lambda: Mp3ArchiveApp._tree_rows(stub)
        stub.tree_toggle_select = (
            lambda row: Mp3ArchiveApp.tree_toggle_select(stub, row))
        # Capture the in-place refresh instead of touching widgets.
        stub._refresh_tree_selection = (
            lambda start: stub._refreshed_at.append(start))
        return stub

    def test_tree_index_is_cached(self):
        """Verifies repeated renders reuse one TreeIndex (no per-tap rebuild)."""
        stub = self._stub_app()
        stub._tree_rows()
        first = stub._tree_index
        self.assertIsNotNone(first)
        stub._tree_rows()
        self.assertIs(stub._tree_index, first)

    def test_folder_toggle_selects_all_then_deselects(self):
        """Verifies a folder tap selects every file under it, then clears."""
        stub = self._stub_app()
        row = types.SimpleNamespace(is_dir=True, key="A", path="", index=0)
        stub.tree_toggle_select(row)
        self.assertEqual(stub._selected, {"/m/A/1.mp3", "/m/A/2.mp3"})
        self.assertEqual(stub.selection_count, 2)
        stub.tree_toggle_select(row)
        self.assertEqual(stub._selected, set())
        self.assertEqual(stub._refreshed_at, [0, 0])

    def test_file_toggle_flips_single_path(self):
        """Verifies a file tap toggles just that path via the in-place path."""
        stub = self._stub_app()
        row = types.SimpleNamespace(is_dir=False, key="",
                                    path="/m/B/3.mp3", index=4)
        stub.tree_toggle_select(row)
        self.assertEqual(stub._selected, {"/m/B/3.mp3"})
        stub.tree_toggle_select(row)
        self.assertEqual(stub._selected, set())
        self.assertEqual(stub._refreshed_at, [4, 4])

    def test_rows_carry_selection_flags(self):
        """Verifies _tree_rows tags rows from the live selection set."""
        stub = self._stub_app()
        stub._expanded = {"A"}
        stub._selected = {"/m/A/1.mp3", "/m/A/2.mp3"}
        rows = stub._tree_rows()
        flags = {r["text"].strip(): r["selected"] for r in rows}
        self.assertTrue(flags["▼ A"])
        self.assertTrue(flags["♪ 1.mp3"])
        self.assertFalse(flags["▶ B"])

    def test_date_sort_mode_orders_folders_by_created(self):
        """Verifies the 날짜 sort mode renders newest folders first."""
        stub = self._stub_app()
        stub._sort_mode = "date"
        stub._files = [
            {"path": "/m/old/1.mp3", "created": "2024-01-01 00:00:00"},
            {"path": "/m/new/2.mp3", "created": "2026-01-01 00:00:00"},
        ]
        self.assertEqual([r["key"] for r in stub._tree_rows()],
                         ["new", "old"])

    def test_name_sort_mode_orders_folders_by_name(self):
        """Verifies every non-date sort mode falls back to folder name order."""
        stub = self._stub_app()
        stub._sort_mode = "title"   # finer modes only apply to files
        stub._files = [
            {"path": "/m/zzz/1.mp3", "created": "2026-01-01 00:00:00"},
            {"path": "/m/aaa/2.mp3", "created": "2024-01-01 00:00:00"},
        ]
        self.assertEqual([r["key"] for r in stub._tree_rows()],
                         ["aaa", "zzz"])


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
