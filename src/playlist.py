"""
playlist.py - Pure, GUI-independent playlist/queue logic.

Holds the play-queue model, play-mode cycling, next/previous index selection,
and ``.list`` serialisation so the Android (and any) front-end can drive a
playlist without embedding the rules in Kivy. Fully unit-testable on the host
(no Kivy/PyQt); randomness is injected so shuffle is deterministic in tests.
"""

import random as _random

# Playback modes, in cycle order.
PLAY_MODES = ["sequential", "repeat_one", "repeat_all", "shuffle"]


def _shuffle_pick(current: int, count: int, rng) -> int:
    """
    Pick a random index for shuffle, avoiding the current one when possible.

    Re-picking the current track makes an explicit Next/Prev look like it did
    nothing, so exclude it when there is an alternative.

    Args:
        current: The current index (may be -1/out of range when nothing played).
        count:   Number of tracks (assumed >= 1).
        rng:     Random source exposing ``randrange``.

    Returns:
        A random index in ``[0, count)`` that differs from *current* whenever
        ``count > 1`` and *current* is a valid index.
    """
    if count <= 1:
        return 0
    if not 0 <= current < count:
        return rng.randrange(count)
    pick = rng.randrange(count - 1)        # choose among the other tracks
    return pick if pick < current else pick + 1


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


def next_index(current: int, count: int, mode: str,
               ended: bool = False, rng=None):
    """
    Choose the next track index for the given play mode.

    Args:
        current: Index of the current track (-1 when nothing has played).
        count:   Number of tracks in the queue.
        mode:    A PLAY_MODES value.
        ended:   True when called because a track finished (auto-advance);
                 False when called by the Next button. Only changes
                 ``sequential``: auto-advance returns None past the last track
                 (stop), while the Next button clamps to the last track.
        rng:     Random source for ``shuffle`` (defaults to the ``random``
                 module); injectable for deterministic tests.

    Returns:
        The next index, or None to stop (sequential auto-advance past the end,
        or an empty queue).
    """
    if count <= 0:
        return None
    rng = rng or _random
    if mode == "repeat_one":
        return current if current >= 0 else 0
    if mode == "repeat_all":
        return (current + 1) % count
    if mode == "shuffle":
        return _shuffle_pick(current, count, rng)
    # sequential
    nxt = current + 1
    if nxt < count:
        return nxt
    return None if ended else count - 1


def prev_index(current: int, count: int, mode: str, rng=None):
    """
    Choose the previous track index for the given play mode (Prev button).

    Args:
        current: Index of the current track (-1 when nothing has played).
        count:   Number of tracks in the queue.
        mode:    A PLAY_MODES value.
        rng:     Random source for ``shuffle``; injectable for tests.

    Returns:
        The previous index, or None when the queue is empty. sequential clamps
        at the first track; repeat_all wraps; repeat_one stays; shuffle random.
    """
    if count <= 0:
        return None
    if current < 0:
        # Nothing has played yet — "previous" sensibly starts at the first
        # track in every mode (avoids repeat_all's (-1-1) % count = count-2).
        return 0
    rng = rng or _random
    if mode == "repeat_one":
        return current
    if mode == "repeat_all":
        return (current - 1) % count
    if mode == "shuffle":
        return _shuffle_pick(current, count, rng)
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
