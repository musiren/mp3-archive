"""
test_output_watch.py - Unit tests for src/output_watch.py (OutputWatch).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from output_watch import NONE, PAUSE, RESUME, OutputWatch


def poll(watch, present, playing=True, noisy_paused=False, times=1):
    """Feed *times* identical polls and return the action of the last one."""
    action = NONE
    for _ in range(times):
        action = watch.update(present, playing, noisy_paused)
    return action


class TestLoss(unittest.TestCase):
    """A Bluetooth output that disappears mid-playback pauses it."""

    def test_pauses_after_consecutive_absent_polls(self):
        """The loss is acted on only once it has lasted ABSENT_POLLS polls."""
        watch = OutputWatch()
        self.assertEqual(poll(watch, True), NONE)
        for _ in range(OutputWatch.ABSENT_POLLS - 1):
            self.assertEqual(poll(watch, False), NONE)
        self.assertEqual(poll(watch, False), PAUSE)

    def test_single_poll_glitch_neither_pauses_nor_resumes(self):
        """One absent poll between present ones changes nothing."""
        watch = OutputWatch()
        poll(watch, True)
        self.assertEqual(poll(watch, False), NONE)
        self.assertEqual(poll(watch, True, noisy_paused=True), NONE)
        # The glitch did not count as a loss, so a later real one still does.
        self.assertEqual(
            poll(watch, False, times=OutputWatch.ABSENT_POLLS), PAUSE)

    def test_pause_fires_only_once(self):
        """Staying absent after the pause does not pause again."""
        watch = OutputWatch()
        poll(watch, True)
        self.assertEqual(
            poll(watch, False, times=OutputWatch.ABSENT_POLLS), PAUSE)
        self.assertEqual(poll(watch, False, times=5), NONE)

    def test_no_pause_when_not_playing(self):
        """A loss while already paused or idle only updates the tracking."""
        watch = OutputWatch()
        poll(watch, True, playing=False)
        self.assertEqual(
            poll(watch, False, playing=False, times=OutputWatch.ABSENT_POLLS),
            NONE)

    def test_no_pause_when_no_output_was_ever_present(self):
        """Playing on the speaker with no Bluetooth device is left alone."""
        watch = OutputWatch()
        self.assertEqual(poll(watch, False, times=10), NONE)


class TestReconnect(unittest.TestCase):
    """The output coming back resumes only a loss-driven pause."""

    def test_resumes_after_a_loss_driven_pause(self):
        """absent -> present with the loss flag set resumes playback."""
        watch = OutputWatch()
        poll(watch, True)
        poll(watch, False, times=OutputWatch.ABSENT_POLLS)
        self.assertEqual(poll(watch, True, playing=False, noisy_paused=True),
                         RESUME)

    def test_does_not_resume_a_manual_pause(self):
        """Reconnecting never revives playback the user stopped."""
        watch = OutputWatch()
        poll(watch, True)
        poll(watch, False, playing=False, times=OutputWatch.ABSENT_POLLS)
        self.assertEqual(poll(watch, True, playing=False, noisy_paused=False),
                         NONE)

    def test_resume_fires_only_on_the_edge(self):
        """Staying connected after the resume does not resume again."""
        watch = OutputWatch()
        poll(watch, True)
        poll(watch, False, times=OutputWatch.ABSENT_POLLS)
        self.assertEqual(poll(watch, True, noisy_paused=True), RESUME)
        self.assertEqual(poll(watch, True, noisy_paused=True, times=3), NONE)

    def test_first_ever_poll_is_not_a_reconnect_without_the_flag(self):
        """Seeing a connected output at startup does nothing by itself."""
        self.assertEqual(poll(OutputWatch(), True), NONE)


class TestBroadcastLoss(unittest.TestCase):
    """lost() mirrors the AUDIO_BECOMING_NOISY path."""

    def test_lost_prevents_a_second_pause(self):
        """After the broadcast pause, the poll does not pause again."""
        watch = OutputWatch()
        poll(watch, True)
        watch.lost()
        self.assertEqual(
            poll(watch, False, playing=False, times=OutputWatch.ABSENT_POLLS + 2),
            NONE)

    def test_lost_makes_the_reconnect_a_clean_edge(self):
        """After lost(), the next present poll is a reconnect and resumes."""
        watch = OutputWatch()
        poll(watch, True)
        watch.lost()
        self.assertEqual(poll(watch, True, playing=False, noisy_paused=True),
                         RESUME)

    def test_lost_resets_a_partial_absence(self):
        """lost() clears a half-counted absence so it cannot double-fire."""
        watch = OutputWatch()
        poll(watch, True)
        poll(watch, False, times=OutputWatch.ABSENT_POLLS - 1)
        watch.lost()
        self.assertEqual(poll(watch, False, playing=False), NONE)


if __name__ == "__main__":
    unittest.main()
