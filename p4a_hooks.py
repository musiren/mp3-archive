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


def _patch_template_text(text):
    """Insert the receiver before </application> in a manifest *template*."""
    if "PlayerWidgetProvider" in text:
        return text, True   # already patched (idempotent)
    if "</application>" not in text:
        return text, False
    return text.replace("</application>", RECEIVER_XML + "    </application>", 1), True


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
        new_text, ok = _patch_template_text(text)
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
