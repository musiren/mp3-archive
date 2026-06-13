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

# Each entry is (marker, xml): the xml is injected before </application>
# unless the marker class is already present (idempotent per receiver).
# WidgetActionReceiver deliberately has NO intent filter: the widget targets
# it with explicit intents, and a filter would double-handle the service's
# own implicit notification broadcasts on older Android versions.
RECEIVERS = [
    ("PlayerWidgetProvider", """
        <receiver android:name="%s.PlayerWidgetProvider" android:exported="false">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
            </intent-filter>
            <meta-data android:name="android.appwidget.provider"
                       android:resource="@xml/widget_player_info" />
        </receiver>
""" % PACKAGE),
    ("WidgetActionReceiver", """
        <receiver android:name="%s.WidgetActionReceiver" android:exported="false" />
""" % PACKAGE),
]


def _is_app_manifest(text):
    """True only for THIS app's rendered manifest (not SDL/library manifests)."""
    return "</application>" in text and "org.kivy.android.PythonActivity" in text


def _inject(path):
    """Insert the missing widget <receiver>s before </application>."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    if not _is_app_manifest(text):
        return False   # a library/template manifest, not the app's
    new_text, _ = _patch_text(text)
    if new_text == text:
        return True    # already injected (idempotent)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
    except OSError:
        return False
    print("p4a_hooks: injected widget receivers into", path)
    return True


def _patch_text(text):
    """
    Insert each missing receiver before </application> in *text*.

    Returns:
        (new_text, ok): ok is False when *text* has no </application> to
        anchor on; receivers already present are skipped individually, so a
        manifest patched by an older hook gains only the new receiver.
    """
    if "</application>" not in text:
        return text, False
    for marker, xml in RECEIVERS:
        if (PACKAGE + "." + marker) in text:
            continue
        text = text.replace("</application>", xml + "    </application>", 1)
    return text, True


def _template_paths():
    """Find the SDL2 AndroidManifest templates (dist copies + p4a package)."""
    paths = []
    for root in (os.getcwd(), os.path.join(os.getcwd(), ".buildozer")):
        if os.path.isdir(root):
            paths += glob.glob(os.path.join(
                root, "**", "templates", "AndroidManifest.tmpl.xml"), recursive=True)
    try:
        import pythonforandroid
        base = os.path.dirname(pythonforandroid.__file__)
        paths += glob.glob(os.path.join(
            base, "bootstraps", "*", "build", "templates",
            "AndroidManifest.tmpl.xml"))
    except Exception:
        pass
    seen = set()
    return [p for p in paths if not (p in seen or seen.add(p))]


def _patch_templates():
    """
    Inject the receiver into the manifest TEMPLATE(s) before p4a renders them.

    p4a renders AndroidManifest.tmpl.xml -> AndroidManifest.xml during the apk
    step, *after* before_apk_build and *before* gradle packages the APK, with
    no hook in between. Patching the template (which exists at before_apk_build)
    makes the rendered manifest contain the receiver.
    """
    patched = 0
    for path in _template_paths():
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        new_text, ok = _patch_text(text)
        if not ok:
            continue
        if new_text != text:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(new_text)
            except OSError:
                continue
            print("p4a_hooks: patched manifest template", path)
        patched += 1
    return patched


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
    """Add the App Widget <receiver> by patching the manifest template.

    The rendered manifest does not exist yet at this point, so patch the
    template that p4a is about to render (the durable fix), and also patch any
    already-rendered manifest just in case.
    """
    print("p4a_hooks: before_apk_build, cwd =", os.getcwd())
    n = _patch_templates()
    print("p4a_hooks: patched", n, "manifest template(s)")
    _inject_into_app_manifests()


def after_apk_build(toolchain):
    """
    Re-patch after build in case the manifest was (re-)rendered post
    before_apk_build. Patching the source manifest then is too late for the
    already-assembled APK, but logs the path so the timing is verifiable.
    """
    print("p4a_hooks: after_apk_build, cwd =", os.getcwd())
    _inject_into_app_manifests()
