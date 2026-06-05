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
    """Tests for Mp3ArchiveApp._app_directory static method."""

    def test_fallback_to_cwd(self):
        """Verifies _app_directory() returns cwd when android.storage is unavailable."""
        from main_window_android import Mp3ArchiveApp
        result = Mp3ArchiveApp._app_directory()
        self.assertEqual(result, os.getcwd())

    def test_uses_android_storage_path(self):
        """Verifies _app_directory() calls app_storage_path() when android.storage is present."""
        fake_android = types.ModuleType("android")
        fake_storage = types.ModuleType("android.storage")
        expected = "/data/user/0/org.musiren.mp3archive/files"
        fake_storage.app_storage_path = lambda: expected
        sys.modules.setdefault("android", fake_android)
        sys.modules["android.storage"] = fake_storage
        try:
            from main_window_android import Mp3ArchiveApp
            result = Mp3ArchiveApp._app_directory()
            self.assertEqual(result, expected)
        finally:
            sys.modules.pop("android", None)
            sys.modules.pop("android.storage", None)


if __name__ == "__main__":
    unittest.main()
