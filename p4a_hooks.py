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


def _toolchain_dist_dirs(toolchain):
    """Best-effort dist directories from the toolchain object (API varies)."""
    dirs = []
    for chain in (("_dist", "dist_dir"), ("ctx", "dist_dir"),
                  ("ctx", "dist", "dist_dir")):
        obj = toolchain
        for attr in chain:
            obj = getattr(obj, attr, None)
        if isinstance(obj, str) and obj:
            dirs.append(obj)
    return dirs


def _candidate_manifests(toolchain):
    """Collect plausible rendered-manifest paths, most specific first."""
    cwd = os.getcwd()
    paths = []
    for dist_dir in _toolchain_dist_dirs(toolchain):
        paths.append(os.path.join(dist_dir, "src", "main", "AndroidManifest.xml"))
    # During this hook p4a's CWD is usually the dist dir itself.
    paths.append(os.path.join(cwd, "src", "main", "AndroidManifest.xml"))
    # Recursive sweeps from the CWD and the buildozer build tree.
    roots = [cwd, os.path.join(cwd, ".buildozer")]
    for root in roots:
        if os.path.isdir(root):
            paths.extend(glob.glob(
                os.path.join(root, "**", "src", "main", "AndroidManifest.xml"),
                recursive=True))
            paths.extend(glob.glob(
                os.path.join(root, "**", "AndroidManifest.xml"),
                recursive=True))
    # De-duplicate, keep order.
    seen = set()
    return [p for p in paths if not (p in seen or seen.add(p))]


def _inject(path):
    """Insert the widget <receiver> before </application> in *path*."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    if "</application>" not in text:
        return False   # not a full app manifest (e.g. a template fragment)
    if (PACKAGE + ".PlayerWidgetProvider") in text:
        return True    # already injected (idempotent)
    text = text.replace("</application>", RECEIVER_XML + "    </application>", 1)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError:
        return False
    print("p4a_hooks: injected widget receiver into", path)
    return True


def before_apk_build(toolchain):
    """Add the App Widget <receiver> to the manifest before the APK is built."""
    print("p4a_hooks: before_apk_build, cwd =", os.getcwd())
    candidates = _candidate_manifests(toolchain)
    print("p4a_hooks: %d manifest candidate(s)" % len(candidates))
    injected = 0
    for path in candidates:
        if os.path.exists(path) and _inject(path):
            injected += 1
    if not injected:
        for path in candidates:
            print("p4a_hooks:   tried", path, "exists=", os.path.exists(path))
        print("p4a_hooks: WARNING - widget receiver NOT injected; "
              "the home-screen widget will be missing")
