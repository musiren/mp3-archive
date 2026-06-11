"""
test_service_ipc.py - Tests for the UI <-> audio-service IPC (de)serialiser.

Runs locally (no Kivy/jnius/device): service_ipc imports only stdlib json and
the pure playlist module (for PLAY_MODES validation).
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import service_ipc as ipc  # noqa: E402


class TestMakeCommand(unittest.TestCase):
    """Verify command payloads are built and normalised correctly."""

    def test_sync_round_trips_index_mode(self):
        """A sync command keeps its index/mode through a round trip."""
        s = ipc.make_command(ipc.OP_SYNC, index=0, mode="shuffle")
        data = ipc.parse_command(s)
        self.assertEqual(data["op"], ipc.OP_SYNC)
        self.assertEqual(data["index"], 0)
        self.assertEqual(data["mode"], "shuffle")

    def test_sync_round_trips_seed_and_position(self):
        """A sync command carries the shuffle seed and the resume position."""
        s = ipc.make_command(ipc.OP_SYNC, index=2, mode="shuffle",
                             seed=987654321, position=42.5)
        data = ipc.parse_command(s)
        self.assertEqual(data["seed"], 987654321)
        self.assertEqual(data["position"], 42.5)

    def test_sync_seed_defaults_to_zero(self):
        """A sync without a seed (or a junk seed) normalises to 0 (unset)."""
        s = ipc.make_command(ipc.OP_SYNC, index=0, mode="shuffle")
        self.assertEqual(ipc.parse_command(s)["seed"], 0)
        s = ipc.make_command(ipc.OP_SYNC, index=0, mode="shuffle", seed="junk")
        self.assertEqual(ipc.parse_command(s)["seed"], 0)

    def test_sync_position_clamped_non_negative(self):
        """A negative sync resume position is clamped to 0.0."""
        s = ipc.make_command(ipc.OP_SYNC, index=0, mode="shuffle", position=-9)
        self.assertEqual(ipc.parse_command(s)["position"], 0.0)

    def test_sync_strips_items_from_wire_payload(self):
        """Items passed to make_command are NOT placed on the wire.

        Items go through the shared queue file (``write_queue_items``); the
        OSC datagram would otherwise blow past the ~64 KB UDP cap for queues
        of a few hundred tracks and be silently dropped.
        """
        items = [{"path": "/a.mp3", "title": "a", "subtitle": "x"}]
        s = ipc.make_command(ipc.OP_SYNC, items=items, index=0, mode="shuffle")
        data = ipc.parse_command(s)
        self.assertNotIn("items", data)
        # The payload should be small (no items embedded).
        self.assertLess(len(s.encode("utf-8")), 200)

    def test_sync_unknown_mode_defaults(self):
        """An unrecognised mode falls back to the first PLAY_MODES value."""
        s = ipc.make_command(ipc.OP_SYNC, index=-1, mode="bogus")
        self.assertEqual(ipc.parse_command(s)["mode"], ipc.PLAY_MODES[0])

    def test_sync_non_int_index_defaults_minus_one(self):
        """A non-integer index normalises to -1."""
        s = ipc.make_command(ipc.OP_SYNC, index="oops")
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


class TestQueueFile(unittest.TestCase):
    """Verify the shared queue-file helpers used to bypass the OSC size cap."""

    def setUp(self):
        """Use a fresh temp directory as the storage dir per test."""
        self._tmp = tempfile.TemporaryDirectory()
        self.storage_dir = self._tmp.name

    def tearDown(self):
        """Remove the temp directory."""
        self._tmp.cleanup()

    def test_round_trips_items(self):
        """write_queue_items + read_queue_items preserves a normalised list."""
        items = [
            {"path": "/a.mp3", "title": "A", "subtitle": "Artist A"},
            {"path": "/b.mp3", "title": "B", "subtitle": "Artist B"},
        ]
        ipc.write_queue_items(self.storage_dir, items)
        self.assertEqual(ipc.read_queue_items(self.storage_dir), items)

    def test_round_trips_korean_unicode(self):
        """Non-ASCII titles survive the file round trip (UTF-8 / ensure_ascii=False)."""
        items = [{"path": "/한.mp3", "title": "노래", "subtitle": "가수 — 노래"}]
        ipc.write_queue_items(self.storage_dir, items)
        self.assertEqual(ipc.read_queue_items(self.storage_dir), items)

    def test_normalises_on_write(self):
        """Items missing a path are dropped; other fields coerced to strings."""
        ipc.write_queue_items(
            self.storage_dir,
            [{"path": "/a.mp3", "title": 5}, {"no_path": True}],
        )
        self.assertEqual(
            ipc.read_queue_items(self.storage_dir),
            [{"path": "/a.mp3", "title": "5", "subtitle": ""}],
        )

    def test_handles_huge_queue(self):
        """The file path bypasses the ~64 KB UDP cap that broke OP_SYNC inline."""
        items = [{"path": f"/song_{i}.mp3",
                  "title": "노래 " + ("가" * 30) + str(i),
                  "subtitle": "Artist — " + ("나" * 30)} for i in range(400)]
        ipc.write_queue_items(self.storage_dir, items)
        out = ipc.read_queue_items(self.storage_dir)
        self.assertEqual(len(out), 400)
        # And the on-disk encoding is comfortably bigger than a UDP datagram.
        size = os.path.getsize(ipc.queue_file_path(self.storage_dir))
        self.assertGreater(size, 70_000)

    def test_read_missing_file_returns_empty(self):
        """A missing queue file yields an empty list, not an exception."""
        self.assertEqual(ipc.read_queue_items(self.storage_dir), [])

    def test_read_malformed_file_returns_empty(self):
        """Garbage JSON in the queue file degrades to an empty list."""
        with open(ipc.queue_file_path(self.storage_dir), "w",
                  encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(ipc.read_queue_items(self.storage_dir), [])

    def test_write_is_atomic(self):
        """write_queue_items leaves no .tmp file behind after success."""
        ipc.write_queue_items(self.storage_dir, [{"path": "/a.mp3"}])
        tmp = ipc.queue_file_path(self.storage_dir) + ".tmp"
        self.assertFalse(os.path.exists(tmp))


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
                           volume=0.5, seed=4242)
        st = ipc.parse_state(s)
        self.assertTrue(st["playing"])
        self.assertEqual(st["path"], "/a.mp3")
        self.assertEqual(st["title"], "a")
        self.assertEqual(st["subtitle"], "x")
        self.assertEqual(st["position"], 10.0)
        self.assertEqual(st["length"], 200.0)
        self.assertEqual(st["index"], 3)
        self.assertEqual(st["volume"], 0.5)
        self.assertEqual(st["seed"], 4242)

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
        self.assertEqual(st["seed"], 0)

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
