"""
test_playlist.py - Tests for the GUI-independent playlist/queue logic.

Runs locally (no Kivy needed); playlist imports only stdlib. Shuffle is tested
with an injected fake rng so the result is deterministic.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playlist import (  # noqa: E402
    PLAY_MODES,
    PlayQueue,
    next_index,
    next_play_mode,
    parse_playlist,
    prev_index,
    serialize_playlist,
)


class _FakeRng:
    """A fake rng whose randrange always returns a fixed index."""

    def __init__(self, value):
        """Store the index randrange() will return."""
        self._value = value

    def randrange(self, _count):
        """Return the canned index regardless of count."""
        return self._value


class TestNextPlayMode(unittest.TestCase):
    """Tests for next_play_mode()."""

    def test_cycles_in_order(self):
        """Verify the mode cycles sequential→repeat_one→repeat_all→shuffle→…"""
        self.assertEqual(next_play_mode("sequential"), "repeat_one")
        self.assertEqual(next_play_mode("repeat_one"), "repeat_all")
        self.assertEqual(next_play_mode("repeat_all"), "shuffle")
        self.assertEqual(next_play_mode("shuffle"), "sequential")

    def test_unknown_mode_restarts_cycle(self):
        """Verify an unknown mode falls back to the first mode."""
        self.assertEqual(next_play_mode("bogus"), PLAY_MODES[0])


class TestNextIndex(unittest.TestCase):
    """Tests for next_index()."""

    def test_empty_queue_returns_none(self):
        """Verify a zero-length queue yields None in every mode."""
        for mode in PLAY_MODES:
            self.assertIsNone(next_index(0, 0, mode))

    def test_sequential_advances(self):
        """Verify sequential goes to the next index mid-queue."""
        self.assertEqual(next_index(1, 5, "sequential"), 2)

    def test_sequential_button_clamps_at_last(self):
        """Verify the Next button clamps to the last track (not None)."""
        self.assertEqual(next_index(4, 5, "sequential", ended=False), 4)

    def test_sequential_autoadvance_stops_after_last(self):
        """Verify auto-advance past the last track returns None (stop)."""
        self.assertIsNone(next_index(4, 5, "sequential", ended=True))

    def test_repeat_one_stays(self):
        """Verify repeat_one returns the same index."""
        self.assertEqual(next_index(3, 5, "repeat_one", ended=True), 3)

    def test_repeat_one_from_none_starts_at_zero(self):
        """Verify repeat_one with no current track starts at 0."""
        self.assertEqual(next_index(-1, 5, "repeat_one"), 0)

    def test_repeat_all_wraps(self):
        """Verify repeat_all wraps from the last track to the first."""
        self.assertEqual(next_index(4, 5, "repeat_all", ended=True), 0)
        self.assertEqual(next_index(2, 5, "repeat_all"), 3)

    def test_shuffle_uses_rng(self):
        """Verify shuffle returns the injected rng's choice."""
        self.assertEqual(next_index(0, 10, "shuffle", rng=_FakeRng(7)), 7)


class TestPrevIndex(unittest.TestCase):
    """Tests for prev_index()."""

    def test_empty_queue_returns_none(self):
        """Verify an empty queue yields None."""
        self.assertIsNone(prev_index(0, 0, "sequential"))

    def test_sequential_clamps_at_first(self):
        """Verify sequential prev clamps at the first track."""
        self.assertEqual(prev_index(0, 5, "sequential"), 0)
        self.assertEqual(prev_index(3, 5, "sequential"), 2)

    def test_repeat_all_wraps_to_last(self):
        """Verify repeat_all prev wraps from the first track to the last."""
        self.assertEqual(prev_index(0, 5, "repeat_all"), 4)

    def test_repeat_one_stays(self):
        """Verify repeat_one prev returns the same index."""
        self.assertEqual(prev_index(2, 5, "repeat_one"), 2)

    def test_shuffle_uses_rng(self):
        """Verify shuffle prev returns the injected rng's choice."""
        self.assertEqual(prev_index(3, 10, "shuffle", rng=_FakeRng(1)), 1)


class TestSerializeParse(unittest.TestCase):
    """Tests for serialize_playlist() / parse_playlist()."""

    def test_serialize_one_path_per_line(self):
        """Verify each path is written on its own newline-terminated line."""
        self.assertEqual(
            serialize_playlist(["/m/a.mp3", "/m/b.mp3"]),
            "/m/a.mp3\n/m/b.mp3\n",
        )

    def test_serialize_empty(self):
        """Verify an empty list serialises to an empty string."""
        self.assertEqual(serialize_playlist([]), "")

    def test_parse_drops_blank_lines(self):
        """Verify parsing skips blank/whitespace-only lines."""
        text = "/m/a.mp3\n\n  \n/m/b.mp3\n"
        self.assertEqual(parse_playlist(text), ["/m/a.mp3", "/m/b.mp3"])

    def test_parse_round_trips_serialize(self):
        """Verify parse(serialize(x)) == x."""
        paths = ["/m/x.mp3", "/m/y.mp3", "/m/z.mp3"]
        self.assertEqual(parse_playlist(serialize_playlist(paths)), paths)

    def test_parse_none_is_empty(self):
        """Verify parsing None yields an empty list."""
        self.assertEqual(parse_playlist(None), [])


class TestPlayQueue(unittest.TestCase):
    """Tests for the PlayQueue model."""

    def test_starts_empty(self):
        """Verify a fresh queue is empty with no current track."""
        q = PlayQueue()
        self.assertTrue(q.is_empty)
        self.assertEqual(len(q), 0)
        self.assertEqual(q.current_index, -1)
        self.assertIsNone(q.current_item())

    def test_add_returns_index_and_grows(self):
        """Verify add() appends and returns the new index."""
        q = PlayQueue()
        self.assertEqual(q.add("a"), 0)
        self.assertEqual(q.add("b"), 1)
        self.assertEqual(len(q), 2)
        self.assertEqual(q.items, ["a", "b"])

    def test_add_many(self):
        """Verify add_many appends several items in order."""
        q = PlayQueue()
        q.add_many(["a", "b", "c"])
        self.assertEqual(q.items, ["a", "b", "c"])

    def test_set_current_and_current_item(self):
        """Verify set_current selects an in-range track."""
        q = PlayQueue()
        q.add_many(["a", "b", "c"])
        q.set_current(1)
        self.assertEqual(q.current_index, 1)
        self.assertEqual(q.current_item(), "b")

    def test_set_current_ignores_out_of_range(self):
        """Verify set_current ignores an out-of-range index."""
        q = PlayQueue()
        q.add_many(["a", "b"])
        q.set_current(5)
        self.assertEqual(q.current_index, -1)

    def test_remove_before_current_shifts_pointer(self):
        """Verify removing an earlier item shifts current_index down by one."""
        q = PlayQueue()
        q.add_many(["a", "b", "c"])
        q.set_current(2)          # current = "c"
        q.remove(0)               # drop "a"
        self.assertEqual(q.current_index, 1)
        self.assertEqual(q.current_item(), "c")

    def test_remove_current_keeps_slot(self):
        """Verify removing the current item keeps the pointer on that slot."""
        q = PlayQueue()
        q.add_many(["a", "b", "c"])
        q.set_current(1)          # current = "b"
        q.remove(1)               # drop "b"; slot 1 now holds "c"
        self.assertEqual(q.current_index, 1)
        self.assertEqual(q.current_item(), "c")

    def test_remove_last_current_clamps(self):
        """Verify removing the last (current) item clamps the pointer."""
        q = PlayQueue()
        q.add_many(["a", "b"])
        q.set_current(1)
        q.remove(1)
        self.assertEqual(q.current_index, 0)
        self.assertEqual(q.current_item(), "a")

    def test_remove_only_item_resets(self):
        """Verify removing the only item empties the queue and resets pointer."""
        q = PlayQueue()
        q.add("a")
        q.set_current(0)
        q.remove(0)
        self.assertTrue(q.is_empty)
        self.assertEqual(q.current_index, -1)

    def test_remove_out_of_range_is_noop(self):
        """Verify removing an out-of-range index changes nothing."""
        q = PlayQueue()
        q.add_many(["a", "b"])
        q.set_current(1)
        q.remove(9)
        self.assertEqual(q.items, ["a", "b"])
        self.assertEqual(q.current_index, 1)

    def test_clear(self):
        """Verify clear empties the queue and resets the pointer."""
        q = PlayQueue()
        q.add_many(["a", "b"])
        q.set_current(1)
        q.clear()
        self.assertTrue(q.is_empty)
        self.assertEqual(q.current_index, -1)


if __name__ == "__main__":
    unittest.main()
