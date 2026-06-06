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


if __name__ == "__main__":
    unittest.main()
