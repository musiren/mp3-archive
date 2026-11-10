"""
test_audio_service.py - Tests for src/audio_service.py (AudioService).

audio_service imports jnius/oscpy at module level and drives Android APIs, so
it cannot normally be imported on the host. These tests import it with those
modules stubbed (a plain Python fake of the few Android classes the tested
paths touch) and put sys.modules back afterwards, so no other test module
ever sees the stubs. What is verified is the service's own decision logic;
how the launcher actually renders the widget is only visible on a device.
"""

import os
import sys
import threading
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# (glyph, title) pushed by every AppWidgetManager.updateAppWidget call.
PAINTED = []

svc = None            # the imported audio_service module (set in setUpModule)
_modules_patch = None


class FakeRemoteViews:
    """RemoteViews stand-in recording the play/pause glyph and the title."""

    def __init__(self, *args):
        """Start with nothing painted."""
        self.glyph = None
        self.title = None

    def setImageViewResource(self, view_id, res):
        """Record the glyph set on the play/pause button."""
        if view_id == "ID_PLAY":
            self.glyph = res

    def setTextViewText(self, view_id, text):
        """Record the title text."""
        if view_id == "ID_TITLE":
            self.title = text

    def __getattr__(self, name):
        """Ignore every other RemoteViews call."""
        return lambda *args, **kwargs: None


class FakeWidgetManager:
    """AppWidgetManager stand-in that records what each repaint pushed."""

    @staticmethod
    def getInstance(ctx):
        """Return a manager whose updateAppWidget appends to PAINTED."""
        return types.SimpleNamespace(
            updateAppWidget=lambda comp, rv: PAINTED.append(
                (rv.glyph, rv.title)))


class FakePlayer:
    """MediaPlayer stand-in whose isPlaying() follows start()/pause()."""

    fail_prepare = False   # make the next prepare() raise (a vanished file)

    def __init__(self):
        """Start stopped."""
        self.playing = False

    def prepare(self):
        """Raise when a load failure is being simulated."""
        if FakePlayer.fail_prepare:
            raise RuntimeError("file vanished")

    def start(self):
        """Begin playing."""
        self.playing = True

    def pause(self):
        """Stop playing, keeping the position."""
        self.playing = False

    def isPlaying(self):
        """Return True while playing."""
        return self.playing

    def release(self):
        """Stop and release."""
        self.playing = False

    def __getattr__(self, name):
        """Ignore every other MediaPlayer call."""
        return lambda *args, **kwargs: None


def _fake_autoclass(name):
    """Return a stand-in for the named Android class."""
    table = {
        "android.widget.RemoteViews": FakeRemoteViews,
        "android.appwidget.AppWidgetManager": FakeWidgetManager,
        "android.media.MediaPlayer": FakePlayer,
        "java.lang.String": lambda text: text,
        "android.os.Build$VERSION": types.SimpleNamespace(SDK_INT=33),
        "android.R$drawable": types.SimpleNamespace(
            ic_media_play="PLAY", ic_media_pause="PAUSE"),
    }
    return table.get(name, mock.MagicMock(name=name))


def setUpModule():
    """Import audio_service against stubbed jnius/oscpy modules."""
    global svc, _modules_patch
    _modules_patch = mock.patch.dict(sys.modules)   # restored on stop()
    _modules_patch.start()
    jnius = types.ModuleType("jnius")
    jnius.autoclass = _fake_autoclass
    jnius.cast = mock.MagicMock()
    jnius.java_method = lambda *args, **kwargs: (lambda func: func)
    jnius.PythonJavaClass = object
    sys.modules["jnius"] = jnius
    for name, attrs in (("oscpy", ()), ("oscpy.client", ("OSCClient",)),
                        ("oscpy.server", ("OSCThreadServer",))):
        module = types.ModuleType(name)
        for attr in attrs:
            setattr(module, attr, mock.MagicMock())
        sys.modules[name] = module
    sys.modules.pop("audio_service", None)
    import audio_service
    svc = audio_service


def tearDownModule():
    """Remove the stubs (and the stub-bound module) from sys.modules."""
    _modules_patch.stop()


def make_service():
    """Build an AudioService without __init__, with the Android helpers stubbed."""
    service = svc.AudioService.__new__(svc.AudioService)
    service._lock = threading.RLock()
    service._service = mock.MagicMock()
    service._player = None
    service._items, service._index = [], -1
    service._seed, service._mode = 1, "sequential"
    service._path = service._title = service._subtitle = ""
    service._paused = service._auto_paused = False
    service._noisy_paused = service._ducked = False
    service._was_playing = False
    service._volume = 1.0
    service._widget_art_path = service._widget_art_bmp = None
    service._focus_listener, service._focus_request = None, None
    # Android-only helpers irrelevant to the decisions under test.
    service._res_id = lambda name, kind: {
        "widget_play_pause": "ID_PLAY", "widget_title": "ID_TITLE"}.get(name, 1)
    service._widget_art_bitmap = lambda: None
    service._content_pi = lambda: None
    service._widget_action_pi = lambda action, code: None
    service._update_session = lambda: None
    service._post_notification = lambda: None
    service._apply_player_volume = lambda: None
    service._request_focus = lambda: None
    service._abandon_focus = lambda: None
    service.push_state = lambda: None
    service._position_length = lambda: (0.0, 0.0)
    return service


class TestWidgetGlyph(unittest.TestCase):
    """The widget's play/pause glyph and title follow the service state."""

    def setUp(self):
        """Clear the paint log and any simulated load failure."""
        PAINTED.clear()
        FakePlayer.fail_prepare = False

    def tearDown(self):
        """Never leak a simulated load failure into another test."""
        FakePlayer.fail_prepare = False

    def test_playing_paints_pause_glyph_and_title(self):
        """Starting a track paints the pause glyph with its title."""
        service = make_service()
        service._play_path("/m/a.mp3", "A", "x")
        self.assertEqual(PAINTED[-1], ("PAUSE", "A"))

    def test_toggle_flips_the_glyph(self):
        """Pausing paints play; resuming paints pause."""
        service = make_service()
        service._play_path("/m/a.mp3", "A", "x")
        service.toggle()
        self.assertEqual(PAINTED[-1][0], "PLAY")
        service.toggle()
        self.assertEqual(PAINTED[-1][0], "PAUSE")

    def test_stop_paints_play_glyph_and_clears_title(self):
        """Stopping paints the play glyph with an empty title."""
        service = make_service()
        service._play_path("/m/a.mp3", "A", "x")
        service.stop()
        self.assertEqual(PAINTED[-1], ("PLAY", ""))

    def test_failed_load_repaints_the_widget_idle(self):
        """A track that fails to load must not leave the old pause glyph up."""
        service = make_service()
        service._play_path("/m/a.mp3", "A", "x")
        PAINTED.clear()
        FakePlayer.fail_prepare = True
        service._play_path("/m/gone.mp3", "G", "x")
        self.assertTrue(PAINTED, "the widget was not repainted after a failed load")
        self.assertEqual(PAINTED[-1], ("PLAY", ""))
        self.assertEqual(service._path, "")


if __name__ == "__main__":
    unittest.main()
