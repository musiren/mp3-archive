"""
net_util.py - Networking helpers shared by the metadata fetchers.

Kept dependency-light (stdlib + optional certifi) and GUI-independent so it can
be unit-tested locally without Kivy/PyQt.
"""

import ssl


def ssl_context() -> ssl.SSLContext:
    """
    Build an SSL context that can verify HTTPS server certificates.

    On python-for-android the system CA bundle CPython expects is absent, so
    HTTPS certificate verification fails (SSLCertVerificationError) unless a CA
    bundle is supplied explicitly. Use certifi's bundled roots when available
    (the Android build ships certifi); otherwise fall back to the platform
    default context, which works on the desktop via the system trust store.

    Returns:
        A configured ssl.SSLContext suitable for urlopen(..., context=...).
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()
