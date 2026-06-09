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


def _is_app_manifest(text):
    """True only for THIS app's rendered manifest (not SDL/library manifests)."""
    return "</application>" in text and "org.kivy.android.PythonActivity" in text


def _inject(path):
    """Insert the widget <receiver> before </application> in the app manifest."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    if not _is_app_manifest(text):
        return False   # a library/template manifest, not the app's
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


def _inject_into_app_manifests():
    """Patch every app manifest found by recursive sweep; return count."""
    injected = 0
    seen = set()
    for root in (os.getcwd(), os.path.join(os.getcwd(), ".buildozer")):
        if not os.path.isdir(root):
            continue
        for path in glob.glob(os.path.join(root, "**", "AndroidManifest.xml"),
                              recursive=True):
            if path in seen:
                continue
            seen.add(path)
            try:
                with open(path, encoding="utf-8") as fh:
                    is_app = _is_app_manifest(fh.read())
            except OSError:
                is_app = False
            print("p4a_hooks:   manifest", path, "is_app=", is_app)
            if is_app and _inject(path):
                injected += 1
    return injected


def before_apk_build(toolchain):
    """Add the App Widget <receiver> to the app manifest before the APK build."""
    print("p4a_hooks: before_apk_build, cwd =", os.getcwd())
    if not _inject_into_app_manifests():
        print("p4a_hooks: WARNING - app manifest not found at before_apk_build")


def after_apk_build(toolchain):
    """
    Re-patch after build in case the manifest was (re-)rendered post
    before_apk_build. Patching the source manifest then is too late for the
    already-assembled APK, but logs the path so the timing is verifiable.
    """
    print("p4a_hooks: after_apk_build, cwd =", os.getcwd())
    _inject_into_app_manifests()
