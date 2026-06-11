"""
test_playlist.py - Tests for the GUI-independent playlist/queue logic.

Runs locally (no Kivy needed); playlist imports only stdlib. Shuffle is a
deterministic seeded permutation, so its tests use fixed seeds.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playlist import (  # noqa: E402
    PLAY_MODES,
    PlayQueue,
    advance,
    new_shuffle_seed,
    next_index,
    next_play_mode,
    parse_playlist,
    prev_index,
    retreat,
    serialize_playlist,
    shuffle_order,
    start_index,
)


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

    def test_no_current_starts_at_first_in_every_mode(self):
        """Verify prev with current=-1 returns 0 (not repeat_all's count-2)."""
        for mode in ("sequential", "repeat_one", "repeat_all"):
            self.assertEqual(prev_index(-1, 5, mode), 0, mode)


class TestShuffleOrder(unittest.TestCase):
    """Tests for the deterministic seeded shuffle order."""

    def test_same_seed_same_order(self):
        """Verify the same (count, seed) always yields the same permutation."""
        self.assertEqual(shuffle_order(20, 1234), shuffle_order(20, 1234))

    def test_is_a_permutation(self):
        """Verify the order contains every index exactly once."""
        self.assertEqual(sorted(shuffle_order(50, 7)), list(range(50)))

    def test_different_seeds_differ(self):
        """Verify different seeds give different orders (for a sane size)."""
        self.assertNotEqual(shuffle_order(50, 1), shuffle_order(50, 2))

    def test_empty_and_negative_counts(self):
        """Verify count <= 0 yields an empty order."""
        self.assertEqual(shuffle_order(0, 5), [])
        self.assertEqual(shuffle_order(-3, 5), [])

    def test_new_seed_is_nonzero(self):
        """Verify generated seeds never collide with the 0 'unset' sentinel."""
        for _ in range(100):
            self.assertGreater(new_shuffle_seed(), 0)

    def test_new_seed_avoids_first(self):
        """Verify avoid_first re-draws until the order starts elsewhere."""
        for _ in range(20):
            seed = new_shuffle_seed(avoid_first=3, count=5)
            self.assertNotEqual(shuffle_order(5, seed)[0], 3)


class TestAdvance(unittest.TestCase):
    """Tests for advance() — the mode-aware next-track chooser."""

    def test_empty_queue_returns_none(self):
        """Verify a zero-length queue yields None in every mode."""
        for mode in PLAY_MODES:
            index, seed = advance(0, 0, mode, 42)
            self.assertIsNone(index)
            self.assertEqual(seed, 42)

    def test_non_shuffle_delegates_and_keeps_seed(self):
        """Verify non-shuffle modes match next_index and keep the seed."""
        self.assertEqual(advance(1, 5, "sequential", 42), (2, 42))
        self.assertEqual(advance(3, 5, "repeat_one", 42), (3, 42))
        self.assertEqual(advance(4, 5, "repeat_all", 42), (0, 42))
        index, seed = advance(4, 5, "sequential", 42, ended=True)
        self.assertIsNone(index)          # auto-advance stops past the end
        self.assertEqual(seed, 42)

    def test_shuffle_follows_seeded_order(self):
        """Verify shuffle steps through the seeded order, seed unchanged."""
        seed = 1234
        order = shuffle_order(5, seed)
        current = -1
        played = []
        for _ in range(5):
            current, seed = advance(current, 5, "shuffle", seed)
            played.append(current)
        self.assertEqual(played, order)   # exactly the fixed order
        self.assertEqual(seed, 1234)      # untouched until the cycle ends

    def test_shuffle_no_repeat_within_cycle(self):
        """Verify no track plays twice before every track has played once."""
        seed = 99
        current = -1
        played = []
        for _ in range(30):
            current, seed = advance(current, 30, "shuffle", seed)
            played.append(current)
        self.assertEqual(sorted(played), list(range(30)))

    def test_shuffle_reseeds_after_full_cycle(self):
        """Verify finishing the order generates a new seed and a new order."""
        seed = 1234
        last = shuffle_order(5, seed)[-1]
        nxt, new_seed = advance(last, 5, "shuffle", seed)
        self.assertNotEqual(new_seed, seed)
        self.assertEqual(nxt, shuffle_order(5, new_seed)[0])
        self.assertNotEqual(nxt, last)    # the last track never replays first

    def test_shuffle_from_idle_starts_order(self):
        """Verify shuffle with no current track starts the order's first slot."""
        seed = 7
        self.assertEqual(advance(-1, 5, "shuffle", seed),
                         (shuffle_order(5, seed)[0], seed))

    def test_shuffle_single_track(self):
        """Verify a one-track queue keeps playing track 0 (reseeding cycles)."""
        index, _seed = advance(-1, 1, "shuffle", 5)
        self.assertEqual(index, 0)
        index, _seed = advance(0, 1, "shuffle", 5)
        self.assertEqual(index, 0)


class TestRetreat(unittest.TestCase):
    """Tests for retreat() — the mode-aware previous-track chooser."""

    def test_empty_queue_returns_none(self):
        """Verify a zero-length queue yields None in every mode."""
        for mode in PLAY_MODES:
            index, seed = retreat(0, 0, mode, 42)
            self.assertIsNone(index)
            self.assertEqual(seed, 42)

    def test_non_shuffle_delegates_and_keeps_seed(self):
        """Verify non-shuffle modes match prev_index and keep the seed."""
        self.assertEqual(retreat(3, 5, "sequential", 42), (2, 42))
        self.assertEqual(retreat(2, 5, "repeat_one", 42), (2, 42))
        self.assertEqual(retreat(0, 5, "repeat_all", 42), (4, 42))

    def test_shuffle_prev_undoes_next(self):
        """Verify prev steps back through the same fixed order as next."""
        seed = 1234
        first, seed = advance(-1, 8, "shuffle", seed)
        second, seed = advance(first, 8, "shuffle", seed)
        back, seed = retreat(second, 8, "shuffle", seed)
        self.assertEqual(back, first)
        self.assertEqual(seed, 1234)

    def test_shuffle_prev_wraps_to_last_slot(self):
        """Verify prev at the order's first slot wraps to its last slot."""
        seed = 1234
        order = shuffle_order(5, seed)
        index, new_seed = retreat(order[0], 5, "shuffle", seed)
        self.assertEqual(index, order[-1])
        self.assertEqual(new_seed, seed)  # going back never reseeds

    def test_shuffle_no_current_starts_order(self):
        """Verify prev with current=-1 returns the order's first slot."""
        seed = 7
        index, _ = retreat(-1, 5, "shuffle", seed)
        self.assertEqual(index, 0)        # falls back to prev_index's 0


class TestStartIndex(unittest.TestCase):
    """Tests for start_index() — the play-from-idle starting track."""

    def test_non_shuffle_starts_at_zero(self):
        """Verify every non-shuffle mode starts at the first track."""
        for mode in ("sequential", "repeat_one", "repeat_all"):
            self.assertEqual(start_index(5, mode, 42), 0, mode)

    def test_shuffle_starts_at_order_head(self):
        """Verify shuffle starts at the seeded order's first slot."""
        seed = 1234
        self.assertEqual(start_index(5, "shuffle", seed),
                         shuffle_order(5, seed)[0])

    def test_empty_queue_returns_zero(self):
        """Verify an empty queue yields 0 (callers guard on emptiness)."""
        self.assertEqual(start_index(0, "shuffle", 42), 0)


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
