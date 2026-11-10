"""
output_watch.py - Pure decision logic for losing / regaining the audio output.

The playback service pauses when a Bluetooth output goes away and resumes when
it comes back. The system's AUDIO_BECOMING_NOISY broadcast is the primary cue,
but whether Android sends it for every kind of loss (out of range, link
timeout, the peer powering off) depends on the device and Bluetooth stack, so
the service also polls the output devices. This module turns those polls into
a decision, with no Android dependency so it is unit-testable on the host.
"""

PAUSE = "pause"
RESUME = "resume"
NONE = "none"


class OutputWatch:
    """
    Tracks whether a Bluetooth audio output is present across polls.

    Feed it each poll with ``update``; it answers whether the service should
    pause, resume or do nothing. A loss only counts once the output has been
    absent for ``ABSENT_POLLS`` consecutive polls, so a one-poll glitch while
    the route is renegotiated never pauses playback.
    """

    # Consecutive absent polls (~0.5 s each) before a loss is acted on.
    ABSENT_POLLS = 2

    def __init__(self) -> None:
        """Start with no output seen yet."""
        self._present = False
        self._absent = 0

    def lost(self) -> None:
        """
        Record that the output is gone because the system said so.

        Called when the AUDIO_BECOMING_NOISY broadcast arrives and the service
        pauses itself. Marking the output absent stops the poll from pausing a
        second time and makes the later reconnect a clean absent -> present
        edge.
        """
        self._present = False
        self._absent = 0

    def update(self, present: bool, playing: bool, noisy_paused: bool) -> str:
        """
        Feed one poll of the output devices and get the action to take.

        Args:
            present:      True when a Bluetooth audio output is connected.
            playing:      True while the player is actively playing.
            noisy_paused: True when the current pause was caused by an output
                          loss (so a reconnect should resume it).

        Returns:
            ``PAUSE`` when a Bluetooth output that was present has been absent
            for ``ABSENT_POLLS`` polls while playing; ``RESUME`` when the
            output reappears after a loss-driven pause; otherwise ``NONE``
            (never pauses when no Bluetooth output was present, and never
            resumes playback the user stopped).
        """
        if present:
            reconnected = not self._present
            self._present = True
            self._absent = 0
            return RESUME if reconnected and noisy_paused else NONE
        if not self._present:
            self._absent = 0   # nothing was connected, so nothing was lost
            return NONE
        self._absent += 1
        if self._absent < self.ABSENT_POLLS:
            return NONE
        self._present = False
        self._absent = 0
        return PAUSE if playing else NONE
