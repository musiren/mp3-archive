# Plan: Pause on Bluetooth Loss (second signal) & Repaint After a Failed Load

Target: the Android playback service (`src/audio_service.py`) plus one new
GUI/Android-independent helper (`src/output_watch.py`).

## Background

Both items come from reviewing the service against two reports:
"pause when the Bluetooth connection drops" and "does the widget's
play/pause glyph follow the state?".

### Bluetooth loss

The pause already exists (commit e6d3b37): the service registers for the
system `AUDIO_BECOMING_NOISY` broadcast and pauses when it arrives, flags the
pause as disconnect-driven, and `tick` polls the audio output routing so it
can resume when a Bluetooth output reappears. The weakness is that the pause
depends on that single broadcast. Whether Android sends it for every kind of
loss (out of range, link timeout, the peer powering off) varies by device and
Bluetooth stack, so a missed broadcast means playback carries on out of the
phone speaker.

`tick` already polls the output devices every ~0.5 s, so the same poll can
detect the loss without the broadcast.

### Widget glyph

`update_widget()` picks the glyph from `_is_playing()` and is reached from
`_refresh_controls()` on play, toggle, pause, resume and stop, and every ~2 s
while playing. Driving the real function with a stubbed Android layer showed
the glyph following every normal transition. The one gap: when a track fails
to load, `_play_path`'s error branch releases the player and clears the track
but never repaints, so the widget (and notification) keep the previous
track's title and the pause glyph while nothing is playing; tapping it then
restarts the queue instead of pausing.

## Design

### 1. `output_watch.OutputWatch` (pure)

A small state machine over the polled "is a Bluetooth output present" flag,
returning what the service should do:

- `update(present, playing, noisy_paused) -> "pause" | "resume" | "none"`
  - present -> absent while playing: `pause`, but only after the output has
    been absent for `ABSENT_POLLS` (2) consecutive polls, so a one-poll route
    glitch never pauses playback.
  - absent -> present while a disconnect-driven pause is outstanding:
    `resume` (the existing behaviour, unchanged).
  - anything else: `none` (never pauses when no Bluetooth output was present,
    never resumes music the user stopped).
- `lost()`: the broadcast already reported the loss; mark the output absent
  so the poll neither pauses a second time nor misses the reconnect edge.

`AudioService._check_bt_reconnect` becomes a thin dispatcher over it
(`_noisy_paused` is set before the poll-driven pause exactly as the broadcast
path does), and `_on_becoming_noisy` calls `lost()` instead of poking
`_bt_present`.

### 2. Repaint after a failed load

`_play_path`'s error branch calls `_refresh_controls()` after clearing the
track, so the widget, notification and MediaSession go idle.

## Known limits

- The poll reports whether a Bluetooth output is *connected*, not whether the
  stream is *routed* to it. If the user routes media to the phone speaker
  while the headset stays connected and the headset then drops, playback
  pauses although the speaker was unaffected. Accepted: it is a pause, not an
  interruption of output, and the routed-device query needs API 33+.
- A service killed by the OS cannot repaint the widget, so a stale glyph can
  remain until the next action. Not addressed here.

## Test updates (same commits as the code)

- `test_output_watch.py` (new): pure state machine — falling edge needs two
  absent polls, a single-poll flicker neither pauses nor resumes, no pause
  when paused/idle, resume only after a disconnect-driven pause, `lost()`
  prevents a double pause and keeps the reconnect edge.
- `test_audio_service.py` (new): the service imported with `jnius`/`oscpy`
  stubbed (restored afterwards so no other test sees the stubs) — a failed
  load repaints the controls idle; the glyph follows play/pause/stop; the
  poll pauses on a missed broadcast and resumes after a reconnect; the
  broadcast path still pauses once.

## Out of scope

- The SoundLoader fallback (no service) has no output-loss handling.
- On-device verification cannot run in this environment (no adb): after the
  branch is built, disconnect a Bluetooth headset mid-playback (switching it
  off, walking out of range, and "Disconnect" in the phone's Bluetooth menu)
  and check the pause and the widget glyph on the phone.
