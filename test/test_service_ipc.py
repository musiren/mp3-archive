"""
test_service_ipc.py - Tests for the UI <-> audio-service IPC (de)serialiser.

Runs locally (no Kivy/jnius/device): service_ipc imports only stdlib json.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import service_ipc as ipc  # noqa: E402


class TestMakeCommand(unittest.TestCase):
    """Verify command payloads are built and normalised correctly."""

    def test_play_round_trips_fields(self):
        """A play command keeps its path/title/subtitle through a round trip."""
        s = ipc.make_command(ipc.OP_PLAY, path="/a.mp3", title="a", subtitle="x")
        data = ipc.parse_command(s)
        self.assertEqual(data["op"], ipc.OP_PLAY)
        self.assertEqual(data["path"], "/a.mp3")
        self.assertEqual(data["title"], "a")
        self.assertEqual(data["subtitle"], "x")

    def test_unknown_op_rejected(self):
        """make_command raises ValueError for an op it does not know."""
        with self.assertRaises(ValueError):
            ipc.make_command("frobnicate")

    def test_volume_is_clamped(self):
        """Volume above 1.0 or below 0.0 is clamped into [0, 1]."""
        self.assertEqual(json.loads(ipc.make_command(ipc.OP_VOLUME, volume=2.5))["volume"], 1.0)
        self.assertEqual(json.loads(ipc.make_command(ipc.OP_VOLUME, volume=-3))["volume"], 0.0)

    def test_volume_non_numeric_defaults_to_zero(self):
        """A non-numeric volume normalises to 0.0 rather than raising."""
        self.assertEqual(json.loads(ipc.make_command(ipc.OP_VOLUME, volume="loud"))["volume"], 0.0)

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

    def test_missing_op_raises(self):
        """A payload with no op raises ValueError."""
        with self.assertRaises(ValueError):
            ipc.parse_command(json.dumps({"path": "/a.mp3"}))


class TestState(unittest.TestCase):
    """Verify state snapshots round-trip and default safely."""

    def test_round_trip(self):
        """make_state -> parse_state preserves every field."""
        s = ipc.make_state(playing=True, path="/a.mp3", title="a",
                           subtitle="x", position=10.0, length=200.0, ended=False)
        st = ipc.parse_state(s)
        self.assertTrue(st["playing"])
        self.assertEqual(st["path"], "/a.mp3")
        self.assertEqual(st["title"], "a")
        self.assertEqual(st["subtitle"], "x")
        self.assertEqual(st["position"], 10.0)
        self.assertEqual(st["length"], 200.0)
        self.assertFalse(st["ended"])

    def test_defaults_when_empty(self):
        """parse_state of an empty object yields a fully-defaulted idle state."""
        st = ipc.parse_state(json.dumps({}))
        self.assertFalse(st["playing"])
        self.assertEqual(st["path"], "")
        self.assertEqual(st["position"], 0.0)
        self.assertEqual(st["length"], 0.0)
        self.assertFalse(st["ended"])

    def test_malformed_payload_yields_idle_state(self):
        """A malformed (non-JSON) state payload degrades to an idle state."""
        st = ipc.parse_state("garbage{")
        self.assertFalse(st["playing"])
        self.assertEqual(st["path"], "")

    def test_negative_values_clamped(self):
        """Negative position/length values are clamped to 0.0 on parse."""
        st = ipc.parse_state(json.dumps({"position": -4, "length": -9}))
        self.assertEqual(st["position"], 0.0)
        self.assertEqual(st["length"], 0.0)

    def test_ended_flag(self):
        """The ended flag survives a round trip."""
        st = ipc.parse_state(ipc.make_state(playing=False, ended=True))
        self.assertTrue(st["ended"])


if __name__ == "__main__":
    unittest.main()
