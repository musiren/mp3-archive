"""
test_net_util.py - Tests for the shared networking helpers.

Runs locally (stdlib only; certifi is optional and the helper falls back
to the platform default context when it is absent).
"""

import os
import ssl
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from net_util import ssl_context  # noqa: E402


class TestSslContext(unittest.TestCase):
    """Tests for ssl_context()."""

    def test_returns_ssl_context(self):
        """Verify ssl_context() returns an ssl.SSLContext instance."""
        self.assertIsInstance(ssl_context(), ssl.SSLContext)

    def test_context_verifies_certificates(self):
        """Verify the context enforces certificate and hostname checks."""
        ctx = ssl_context()
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)


if __name__ == "__main__":
    unittest.main()
