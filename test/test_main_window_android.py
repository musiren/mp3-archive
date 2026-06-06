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
        """Verifies Builder.load_string(KV) returns a widget with toolbar/progress_bar/status_label/mp3_list ids."""
        from kivy.lang import Builder
        from main_window_android import KV
        root = Builder.load_string(KV)
        self.assertIsNotNone(root, "Builder.load_string returned None — KV has no root widget")
        for ident in ("toolbar", "progress_bar", "status_label", "mp3_list"):
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


if __name__ == "__main__":
    unittest.main()
