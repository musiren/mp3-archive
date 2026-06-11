"""
playlist.py - Pure, GUI-independent playlist/queue logic.

Holds the play-queue model, play-mode cycling, next/previous index selection,
and ``.list`` serialisation so the Android (and any) front-end can drive a
playlist without embedding the rules in Kivy. Fully unit-testable on the host
(no Kivy/PyQt).

Shuffle is a deterministic, seeded permutation of the queue (see
``shuffle_order``): for a given (seed, count) the whole play order is fixed,
so next/prev walk the same order both ways and no track repeats until every
track has played once. The seed only changes when the queue changes, when
shuffle mode is re-entered, or when the order has been exhausted — the caller
owns those triggers and threads the seed through ``advance``/``retreat``.
"""

import random as _random

# Playback modes, in cycle order.
PLAY_MODES = ["sequential", "repeat_one", "repeat_all", "shuffle"]


def new_shuffle_seed(avoid_first: int = -1, count: int = 0) -> int:
    """
    Generate a fresh, non-zero shuffle seed.

    Zero is reserved as the "no seed yet" sentinel on the IPC wire, so seeds
    are drawn from [1, 2**31).

    Args:
        avoid_first: When >= 0 (and *count* > 1), re-draw the seed until the
            new order does not START with this index — used when a cycle ends
            so the last-played track is not immediately replayed.
        count:       Queue length the order will be built for (only needed
            together with *avoid_first*).

    Returns:
        A random integer seed in [1, 2**31).
    """
    seed = _random.randrange(1, 2 ** 31)
    if avoid_first >= 0 and count > 1:
        while shuffle_order(count, seed)[0] == avoid_first:
            seed = _random.randrange(1, 2 ** 31)
    return seed


def shuffle_order(count: int, seed: int) -> list:
    """
    Return the deterministic shuffle play order for a queue of *count* tracks.

    The same (count, seed) pair always yields the same permutation, so the UI
    process and the playback-service process agree on the order by sharing
    only the seed. Duplicate tracks in the queue occupy distinct indices and
    therefore distinct slots in the order.

    Args:
        count: Number of tracks in the queue.
        seed:  The shuffle seed (see ``new_shuffle_seed``).

    Returns:
        A permutation of ``range(count)`` (empty for count <= 0).
    """
    if count <= 0:
        return []
    order = list(range(count))
    _random.Random(seed).shuffle(order)
    return order


def _shuffle_advance(current: int, count: int, seed: int):
    """
    Step forward through the seeded shuffle order.

    Args:
        current: The current queue index (-1/out of range when nothing played).
        count:   Number of tracks in the queue (assumed >= 1).
        seed:    The active shuffle seed.

    Returns:
        ``(index, seed)``: the next queue index in the order. When *current*
        is the last slot of the order the cycle is complete, so a fresh seed
        (whose order does not start with *current*) is generated and the new
        order begins at its first slot.
    """
    order = shuffle_order(count, seed)
    if not 0 <= current < count:
        return order[0], seed
    pos = order.index(current)
    if pos + 1 < count:
        return order[pos + 1], seed
    # Every track has played once: build a fresh order for the next cycle.
    seed = new_shuffle_seed(avoid_first=current, count=count)
    return shuffle_order(count, seed)[0], seed


def _shuffle_retreat(current: int, count: int, seed: int):
    """
    Step backward through the seeded shuffle order.

    Args:
        current: The current queue index (-1/out of range when nothing played).
        count:   Number of tracks in the queue (assumed >= 1).
        seed:    The active shuffle seed.

    Returns:
        ``(index, seed)``: the previous queue index in the order, wrapping
        from the first slot to the last (the seed never changes — going back
        must retrace the same fixed order).
    """
    order = shuffle_order(count, seed)
    if not 0 <= current < count:
        return order[0], seed
    pos = order.index(current)
    return order[pos - 1], seed          # pos 0 wraps to the last slot


def advance(current: int, count: int, mode: str, seed: int,
            ended: bool = False):
    """
    Choose the next track for any play mode, threading the shuffle seed.

    This is the single entry point the UI and the playback service use for
    "next" (button or auto-advance); non-shuffle modes delegate to
    ``next_index`` and pass the seed through unchanged.

    Args:
        current: Index of the current track (-1 when nothing has played).
        count:   Number of tracks in the queue.
        mode:    A PLAY_MODES value.
        seed:    The active shuffle seed (ignored outside shuffle mode).
        ended:   True when called because a track finished (see next_index).

    Returns:
        ``(index, seed)`` where index is the next queue index or None to stop,
        and seed is the (possibly regenerated) shuffle seed.
    """
    if count <= 0:
        return None, seed
    if mode == "shuffle":
        return _shuffle_advance(current, count, seed)
    return next_index(current, count, mode, ended=ended), seed


def retreat(current: int, count: int, mode: str, seed: int):
    """
    Choose the previous track for any play mode, threading the shuffle seed.

    Args:
        current: Index of the current track (-1 when nothing has played).
        count:   Number of tracks in the queue.
        mode:    A PLAY_MODES value.
        seed:    The active shuffle seed (ignored outside shuffle mode).

    Returns:
        ``(index, seed)`` where index is the previous queue index or None when
        the queue is empty; the seed is always returned unchanged.
    """
    if count <= 0:
        return None, seed
    if mode == "shuffle" and 0 <= current < count:
        return _shuffle_retreat(current, count, seed)
    return prev_index(current, count, mode), seed


def start_index(count: int, mode: str, seed: int) -> int:
    """
    Pick the queue index to start from when play is pressed while idle.

    Shuffle starts at the first slot of the seeded order (so the whole cycle
    is played without repeats); every other mode starts at the first track.

    Args:
        count: Number of tracks in the queue (assumed >= 1).
        mode:  A PLAY_MODES value.
        seed:  The active shuffle seed.

    Returns:
        The queue index to play first.
    """
    if count <= 0:
        return 0
    if mode == "shuffle":
        return shuffle_order(count, seed)[0]
    return 0


def next_play_mode(mode: str) -> str:
    """
    Return the next play mode in the cycle.

    Args:
        mode: The current mode (an unknown value restarts the cycle).

    Returns:
        sequential → repeat_one → repeat_all → shuffle → sequential …
    """
    try:
        idx = PLAY_MODES.index(mode)
    except ValueError:
        return PLAY_MODES[0]
    return PLAY_MODES[(idx + 1) % len(PLAY_MODES)]


def next_index(current: int, count: int, mode: str, ended: bool = False):
    """
    Choose the next track index for the non-shuffle play modes.

    Shuffle needs the seed threaded through, so it lives in ``advance`` —
    use that as the general entry point; an unknown (or "shuffle") mode here
    falls through to sequential.

    Args:
        current: Index of the current track (-1 when nothing has played).
        count:   Number of tracks in the queue.
        mode:    A PLAY_MODES value.
        ended:   True when called because a track finished (auto-advance);
                 False when called by the Next button. Only changes
                 ``sequential``: auto-advance returns None past the last track
                 (stop), while the Next button clamps to the last track.

    Returns:
        The next index, or None to stop (sequential auto-advance past the end,
        or an empty queue).
    """
    if count <= 0:
        return None
    if mode == "repeat_one":
        return current if current >= 0 else 0
    if mode == "repeat_all":
        return (current + 1) % count
    # sequential
    nxt = current + 1
    if nxt < count:
        return nxt
    return None if ended else count - 1


def prev_index(current: int, count: int, mode: str):
    """
    Choose the previous track index for the non-shuffle play modes.

    Shuffle needs the seed threaded through, so it lives in ``retreat`` —
    use that as the general entry point; an unknown (or "shuffle") mode here
    falls through to sequential.

    Args:
        current: Index of the current track (-1 when nothing has played).
        count:   Number of tracks in the queue.
        mode:    A PLAY_MODES value.

    Returns:
        The previous index, or None when the queue is empty. sequential clamps
        at the first track; repeat_all wraps; repeat_one stays.
    """
    if count <= 0:
        return None
    if current < 0:
        # Nothing has played yet — "previous" sensibly starts at the first
        # track in every mode (avoids repeat_all's (-1-1) % count = count-2).
        return 0
    if mode == "repeat_one":
        return current
    if mode == "repeat_all":
        return (current - 1) % count
    # sequential
    return max(0, current - 1)


def serialize_playlist(paths: list) -> str:
    """
    Serialise a list of file paths to ``.list`` text (one path per line).

    Args:
        paths: Absolute file paths in queue order.

    Returns:
        Newline-terminated text, one path per line.
    """
    return "".join(f"{p}\n" for p in paths)


def parse_playlist(text: str) -> list:
    """
    Parse ``.list`` text into a list of file paths.

    Blank lines are dropped and each path is stripped of trailing newline /
    surrounding whitespace. Whether each path still exists is the caller's
    concern (the UI skips missing files on load).

    Args:
        text: The full contents of a ``.list`` file.

    Returns:
        A list of path strings in file order.
    """
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


class PlayQueue:
    """
    An ordered play queue with a current-track pointer.

    Items are arbitrary (the front-end uses file-info dicts carrying at least a
    ``path`` for playback plus filename/artist/title for display). All index
    bookkeeping — especially keeping ``current_index`` pointing at the same
    track after a removal — lives here so the UI stays thin.
    """

    def __init__(self) -> None:
        """Start with an empty queue and no current track."""
        self._items: list = []
        self._current: int = -1

    @property
    def items(self) -> list:
        """Return the queued items in order (the live list)."""
        return self._items

    @property
    def current_index(self) -> int:
        """Return the current track index, or -1 when none is selected."""
        return self._current

    @property
    def is_empty(self) -> bool:
        """Return True when the queue holds no items."""
        return not self._items

    def __len__(self) -> int:
        """Return the number of queued items."""
        return len(self._items)

    def current_item(self):
        """Return the current item, or None when the index is out of range."""
        if 0 <= self._current < len(self._items):
            return self._items[self._current]
        return None

    def add(self, item) -> int:
        """
        Append an item to the end of the queue.

        Args:
            item: The item to enqueue.

        Returns:
            The index the item was added at.
        """
        self._items.append(item)
        return len(self._items) - 1

    def add_many(self, items) -> None:
        """Append several items to the end of the queue, in order."""
        for item in items:
            self._items.append(item)

    def set_current(self, index: int) -> None:
        """
        Set the current track index when it is in range (else leave unchanged).

        Args:
            index: The index to make current.
        """
        if 0 <= index < len(self._items):
            self._current = index

    def remove(self, index: int) -> None:
        """
        Remove the item at *index*, keeping ``current_index`` on the same track.

        Removing an item before the current one shifts the pointer down by one;
        removing the current item leaves the pointer in place (now referring to
        the item that took its slot, clamped to the new end), so playback
        continues sensibly. A no-op for an out-of-range index.

        Args:
            index: Index of the item to remove.
        """
        if not (0 <= index < len(self._items)):
            return
        del self._items[index]
        if not self._items:
            self._current = -1
        elif index < self._current:
            self._current -= 1
        elif index == self._current:
            # Keep pointing at the same slot, clamped to the new last index.
            self._current = min(self._current, len(self._items) - 1)

    def clear(self) -> None:
        """Empty the queue and reset the current pointer."""
        self._items = []
        self._current = -1
