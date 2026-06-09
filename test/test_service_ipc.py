"""
test_service_ipc.py - Tests for the UI <-> audio-service IPC (de)serialiser.

Runs locally (no Kivy/jnius/device): service_ipc imports only stdlib json and
the pure playlist module (for PLAY_MODES validation).
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import service_ipc as ipc  # noqa: E402


class TestMakeCommand(unittest.TestCase):
    """Verify command payloads are built and normalised correctly."""

    def test_sync_round_trips_items_index_mode(self):
        """A sync command keeps its items/index/mode through a round trip."""
        items = [{"path": "/a.mp3", "title": "a", "subtitle": "x"}]
        s = ipc.make_command(ipc.OP_SYNC, items=items, index=0, mode="shuffle")
        data = ipc.parse_command(s)
        self.assertEqual(data["op"], ipc.OP_SYNC)
        self.assertEqual(data["index"], 0)
        self.assertEqual(data["mode"], "shuffle")
        self.assertEqual(data["items"], items)

    def test_sync_normalises_items(self):
        """Items are coerced to path/title/subtitle dicts; bad entries dropped."""
        s = ipc.make_command(ipc.OP_SYNC,
                             items=[{"path": "/a.mp3", "title": "a"},
                                    {"no_path": 1}, "junk"])
        data = ipc.parse_command(s)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0],
                         {"path": "/a.mp3", "title": "a", "subtitle": ""})

    def test_sync_unknown_mode_defaults(self):
        """An unrecognised mode falls back to the first PLAY_MODES value."""
        s = ipc.make_command(ipc.OP_SYNC, items=[], index=-1, mode="bogus")
        self.assertEqual(ipc.parse_command(s)["mode"], ipc.PLAY_MODES[0])

    def test_sync_non_int_index_defaults_minus_one(self):
        """A non-integer index normalises to -1."""
        s = ipc.make_command(ipc.OP_SYNC, items=[], index="oops")
        self.assertEqual(ipc.parse_command(s)["index"], -1)

    def test_unknown_op_rejected(self):
        """make_command raises ValueError for an op it does not know."""
        with self.assertRaises(ValueError):
            ipc.make_command("frobnicate")

    def test_volume_is_clamped(self):
        """Volume above 1.0 or below 0.0 is clamped into [0, 1]."""
        self.assertEqual(json.loads(ipc.make_command(ipc.OP_VOLUME, volume=2.5))["volume"], 1.0)
        self.assertEqual(json.loads(ipc.make_command(ipc.OP_VOLUME, volume=-3))["volume"], 0.0)

    def test_seek_position_non_negative(self):
        """A negative seek position is clamped to 0.0."""
        self.assertEqual(json.loads(ipc.make_command(ipc.OP_SEEK, position=-5))["position"], 0.0)

    def test_seek_position_preserved(self):
        """A valid seek position survives the round trip."""
        self.assertEqual(json.loads(ipc.make_command(ipc.OP_SEEK, position=12.5))["position"], 12.5)


class TestParseCommand(unittest.TestCase):
    """Verify command parsing validates its input."""

    def test_invalid_json_raises(self):
        """Non-JSON input raises ValueError."""
        with self.assertRaises(ValueError):
            ipc.parse_command("{not json")

    def test_non_object_raises(self):
        """A JSON value that is not an object raises ValueError."""
        with self.assertRaises(ValueError):
            ipc.parse_command("[1, 2, 3]")

    def test_unknown_op_raises(self):
        """A payload with an unknown op raises ValueError."""
        with self.assertRaises(ValueError):
            ipc.parse_command(json.dumps({"op": "nope"}))


class TestNormalizeItems(unittest.TestCase):
    """Verify queue-item coercion."""

    def test_non_list_returns_empty(self):
        """A non-list items value normalises to an empty list."""
        self.assertEqual(ipc.normalize_items("nope"), [])
        self.assertEqual(ipc.normalize_items(None), [])

    def test_drops_entries_without_path(self):
        """Entries lacking a path are dropped."""
        self.assertEqual(ipc.normalize_items([{"title": "x"}]), [])

    def test_coerces_fields_to_strings(self):
        """All kept fields become strings with the canonical keys."""
        out = ipc.normalize_items([{"path": "/a", "title": 5}])
        self.assertEqual(out, [{"path": "/a", "title": "5", "subtitle": ""}])


class TestState(unittest.TestCase):
    """Verify state snapshots round-trip and default safely."""

    def test_round_trip(self):
        """make_state -> parse_state preserves every field."""
        s = ipc.make_state(playing=True, path="/a.mp3", title="a",
                           subtitle="x", position=10.0, length=200.0, index=3,
                           volume=0.5)
        st = ipc.parse_state(s)
        self.assertTrue(st["playing"])
        self.assertEqual(st["path"], "/a.mp3")
        self.assertEqual(st["title"], "a")
        self.assertEqual(st["subtitle"], "x")
        self.assertEqual(st["position"], 10.0)
        self.assertEqual(st["length"], 200.0)
        self.assertEqual(st["index"], 3)
        self.assertEqual(st["volume"], 0.5)

    def test_volume_clamped_in_state(self):
        """A state volume above 1.0 is clamped on parse."""
        self.assertEqual(ipc.parse_state(json.dumps({"volume": 9}))["volume"], 1.0)

    def test_defaults_when_empty(self):
        """parse_state of an empty object yields a fully-defaulted idle state."""
        st = ipc.parse_state(json.dumps({}))
        self.assertFalse(st["playing"])
        self.assertEqual(st["path"], "")
        self.assertEqual(st["position"], 0.0)
        self.assertEqual(st["length"], 0.0)
        self.assertEqual(st["index"], -1)
        self.assertEqual(st["volume"], 1.0)

    def test_malformed_payload_yields_idle_state(self):
        """A malformed (non-JSON) state payload degrades to an idle state."""
        st = ipc.parse_state("garbage{")
        self.assertFalse(st["playing"])
        self.assertEqual(st["path"], "")
        self.assertEqual(st["index"], -1)

    def test_negative_values_clamped(self):
        """Negative position/length values are clamped to 0.0 on parse."""
        st = ipc.parse_state(json.dumps({"position": -4, "length": -9}))
        self.assertEqual(st["position"], 0.0)
        self.assertEqual(st["length"], 0.0)


if __name__ == "__main__":
    unittest.main()
