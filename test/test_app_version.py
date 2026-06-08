"""
test_app_version.py - Tests for the bundled version module.

src/app_version.py is generated from NEWS by assets/make_version.py and is the
fallback the Android About dialog reads when NEWS is not packaged into the APK.
These tests run locally (no Kivy/PyQt needed): app_version is a plain constant
and ui_util imports only stdlib.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ui_util import latest_news_version  # noqa: E402

_ROOT = os.path.join(os.path.dirname(__file__), "..")


class TestAppVersion(unittest.TestCase):
    """Verify the bundled version constant stays in sync with NEWS."""

    def test_version_constant_exists(self):
        """app_version.VERSION is a non-empty string."""
        import app_version
        self.assertIsInstance(app_version.VERSION, str)
        self.assertTrue(app_version.VERSION)

    def test_version_looks_like_a_release_tag(self):
        """VERSION matches the vYYYY... release-tag shape, not the bare fallback."""
        import app_version
        self.assertRegex(app_version.VERSION, r"^v\d{6,8}$")

    def test_version_matches_latest_news(self):
        """The generated constant equals NEWS's newest version header.

        Guards against editing NEWS without re-running assets/make_version.py.
        """
        import app_version
        with open(os.path.join(_ROOT, "NEWS"), encoding="utf-8") as fh:
            expected = latest_news_version(fh.read())
        self.assertEqual(app_version.VERSION, expected)


if __name__ == "__main__":
    unittest.main()
