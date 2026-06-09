"""
python-for-android build hooks for the MP3 Archive home-screen widget.

p4a v2024.01.21 has no buildozer key that adds an ``<application>``-child
``<receiver>`` to the manifest (``extra_manifest_application_arguments`` only
adds attributes; ``add_activities`` only emits bare ``<activity>``; the proper
``extra_manifest_application_xml`` PR is unmerged). So inject the App Widget
receiver into the rendered AndroidManifest.xml during the build, before the APK
is packaged.

Referenced from buildozer.spec as ``p4a.hook = p4a_hooks.py``.
"""

import glob
import os

PACKAGE = "org.musiren.mp3archive"

RECEIVER_XML = """
        <receiver android:name="%s.PlayerWidgetProvider" android:exported="false">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
            </intent-filter>
            <meta-data android:name="android.appwidget.provider"
                       android:resource="@xml/widget_player_info" />
        </receiver>
""" % PACKAGE


def _candidate_manifests(toolchain):
    """Yield possible rendered-manifest paths, most specific first."""
    paths = []
    try:
        dist_dir = getattr(getattr(toolchain, "_dist", None), "dist_dir", None)
        if dist_dir:
            paths.append(os.path.join(dist_dir, "src", "main", "AndroidManifest.xml"))
    except Exception:
        pass
    # Fallback: the rendered manifest under the build dists (CWD = project root).
    paths.extend(glob.glob(os.path.join(
        ".buildozer", "android", "platform", "build-*", "dists", "*",
        "src", "main", "AndroidManifest.xml")))
    # De-duplicate while preserving order.
    seen = set()
    return [p for p in paths if not (p in seen or seen.add(p))]


def _inject(path):
    """Insert the widget <receiver> before </application> in *path*."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    if (PACKAGE + ".PlayerWidgetProvider") in text:
        return True   # already injected (idempotent)
    if "</application>" not in text:
        return False
    text = text.replace("</application>", RECEIVER_XML + "    </application>", 1)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print("p4a_hooks: injected widget receiver into", path)
    return True


def before_apk_build(toolchain):
    """Add the App Widget <receiver> to the manifest before the APK is built."""
    injected = False
    for path in _candidate_manifests(toolchain):
        if os.path.exists(path) and _inject(path):
            injected = True
    if not injected:
        print("p4a_hooks: WARNING - widget receiver NOT injected "
              "(manifest not found); the home-screen widget will be missing")
