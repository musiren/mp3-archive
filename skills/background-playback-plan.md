# Background Playback (Android Foreground Service) — Plan

## Goal

Make audio keep playing reliably when the MP3 Archive Android app is in the
background or the screen is off — the proper Android way, with a foreground
service, a persistent notification, and audio-focus handling.

## Current state (why it does not work today)

- Playback runs **in the UI process** via `kivy.core.audio.SoundLoader`
  (`src/main_window_android.py`).
- `buildozer.spec` has **no service**, and permissions are only
  `READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, READ_MEDIA_AUDIO,
  MANAGE_EXTERNAL_STORAGE, INTERNET` — no `FOREGROUND_SERVICE`, `WAKE_LOCK`,
  or `POST_NOTIFICATIONS`.
- No `on_pause` handler, no audio focus, no media notification.
- Result: when the app is backgrounded (especially screen-off / Doze /
  memory pressure) the OS suspends or kills the process and audio stops.

## Why a foreground service

Since Android 8 (API 26) background processes are aggressively limited. The
only sanctioned way to keep audio running while backgrounded is a **foreground
service** that calls `startForeground()` with an ongoing notification. A p4a
service runs in a **separate OS process** with its own Python interpreter, so
the audio engine must live inside the service, and the UI must talk to it via
IPC.

## Architecture decision

1. **Playback moves into the service.** `SoundLoader` is tied to the UI/window
   context and does not work in a service process, so the service plays audio
   with **`android.media.MediaPlayer` via pyjnius**.
2. **The service is the source of truth** for the queue and playback state.
   The UI becomes a thin client: it sends commands and renders the state the
   service pushes back. This way playback survives the UI being killed.
3. **Reuse the pure logic.** `src/playlist.py` (`PlayQueue`, `next_index`,
   `prev_index`, play modes) is GUI-independent and already unit-tested — it is
   imported by **both** the UI and the service so queue semantics stay
   identical. No audio/Kivy code is added to `playlist.py`.
4. **IPC = oscpy.** `oscpy` is the Kivy-team OSC library used in the official
   p4a service examples; it is pure Python (no recipe needed). The UI and the
   service each run an `OSCThreadServer` on `127.0.0.1` and send to each other.
   Only small data crosses OSC: file **paths**, indices, scalars — never album
   art bytes (the UI reads art from the path itself, as it does today).
5. **Keep the initial service argument tiny.** `PYTHON_SERVICE_ARGUMENT` can be
   truncated, so it carries only the UI's OSC reply port. The queue is sent
   over OSC after the service is up, never embedded in the start argument.

## OSC protocol (draft)

UI → service (commands):
`/enqueue <path>...`, `/play_index <i>`, `/toggle`, `/pause`, `/stop`,
`/next`, `/prev`, `/seek <sec>`, `/volume <0..1>`, `/set_mode <mode>`,
`/load_queue <path>...` (replace), `/clear`, `/ping`.

Service → UI (state push, coalesced ~2x/sec while playing):
`/state` with: now-playing path, title, subtitle, is_playing, position_sec,
length_sec, current_index, play_mode, queue (list of paths). `/ended` is folded
into `/state`. The UI rebuilds the queue list, now-playing highlight, position
bar, play/pause icon, and mode button from `/state`.

## buildozer.spec changes

- `requirements = ...,oscpy`
- `services = audioplayback:src/audio_service.py:foreground:sticky:foregroundServiceType=mediaPlayback`
  - The auto-generated class is expected to be
    `org.musiren.mp3archive.ServiceAudioplayback` — **verify in Stage 0**.
- `android.permissions = <existing>,FOREGROUND_SERVICE,FOREGROUND_SERVICE_MEDIA_PLAYBACK,POST_NOTIFICATIONS,WAKE_LOCK`
  - `foregroundServiceType=mediaPlayback` / `FOREGROUND_SERVICE_MEDIA_PLAYBACK`
    are only *required* at API 34; harmless at the current `android.api = 33`
    and forward-compatible when target is bumped for Play.
- Possibly `android.gradle_dependencies = androidx.media:media:1.7.0` — only if
  Stage 3 (MediaSession / MediaStyle controls) needs it. Not for Stages 0–2.

## Stages (each Android change → on-device verify routine)

### Stage 0 — Spike: verify p4a service mechanics on-device  *(blocking)*
Smallest possible service to resolve the critic's Tier-1 unknowns before the
real refactor:
- Declare the service; from the UI `autoclass` the generated class and `.start`
  it. **Confirm the exact class name.**
- In the service: create a `MediaPlayer`, play one passed-in file; confirm MP3
  plays and **keeps playing when the app is backgrounded / screen off**.
- Confirm whether `:foreground` makes p4a call `startForeground` automatically
  and a notification shows; if not, call it explicitly via jnius.
- Stand up an `oscpy` round-trip (`/ping` → `/pong`).
- Add `POST_NOTIFICATIONS` + request it at runtime (API 33+).
Outcome: a verified skeleton + notes that lock down the rest of the plan.

### Stage 1 — Service playback engine + UI client  *(the big refactor)*
- `src/audio_service.py`: `MediaPlayer` wrapper (load/play/pause/stop/seek/
  volume/duration/position + `OnCompletionListener`), the queue via
  `playlist.PlayQueue`, an `oscpy` server handling all commands, and a coalesced
  `/state` pusher.
- UI: OSC client + server; start the service on app start; **replace every
  direct `SoundLoader`/`sound.*` call** with an OSC command; drive the player UI
  (now-playing, position bar, queue highlight, play/pause, mode, save/load/clear)
  from `/state`. Handle app resume: re-fetch the service via `autoclass` and
  re-sync from `/state` (do not blindly re-`start`).
- Likely several commits: (a) service engine, (b) UI OSC plumbing + start/stop
  lifecycle, (c) migrate transport controls, (d) migrate queue ops + save/load.

### Stage 2 — Stay-alive + audio focus + wake lock
- Ensure the foreground notification reliably shows (channel created in the
  service; `POST_NOTIFICATIONS` granted) so the OS will not kill the service.
- `MediaPlayer.setWakeMode(PARTIAL_WAKE_LOCK)` + `WAKE_LOCK` permission for
  screen-off playback.
- Audio focus: `AudioManager.requestAudioFocus`; pause on `LOSS`, resume on
  `GAIN`, duck (lower volume) on `LOSS_TRANSIENT_CAN_DUCK`. Implement the
  listener with `pyjnius` `PythonJavaClass`; handle it inside the service.

### Stage 3 — Media notification + lock-screen controls  *(enhancement, optional)*
- `MediaSessionCompat` + `NotificationCompat.MediaStyle` notification with
  play/pause/prev/next actions and lock-screen / headset / Bluetooth controls.
- Route button taps back to the service (PendingIntent → broadcast/action).
- Add `androidx.media` gradle dependency. This is the heaviest, most
  device-specific piece and can ship after Stages 0–2 already deliver working
  background playback.

## Open questions to resolve in Stage 0 (from the research critique)

1. Exact generated service class name for `autoclass`.
2. Does `:foreground` auto-call `startForeground`, or must the service do it?
3. Does `MediaPlayer.setDataSource` play our MP3/FLAC/etc. on API 33?
4. Is `POST_NOTIFICATIONS` enough at runtime for the foreground notification?
5. Does declaring `FOREGROUND_SERVICE_MEDIA_PLAYBACK` at `android.api = 33`
   build and run cleanly?
6. `oscpy` builds and imports under p4a v2024.01.21.

## Testing & verification

- **Unit tests (local, non-GUI):** any new pure helper (e.g. an OSC
  command/`/state` (de)serializer) gets `test/test_*.py` coverage. `playlist.py`
  tests already cover queue semantics. The `MediaPlayer`/jnius/service code
  cannot be unit-tested off-device (like the existing Kivy UI) and is skipped.
- **On-device (mandatory):** per the project's Android routine — push, watch the
  `Build` workflow's `android` job, install the APK, and verify on the device:
  audio continues with the app backgrounded and with the screen off, the
  notification persists, and (Stage 2+) playback pauses when another app takes
  audio focus. The dev phone is currently disconnected, so installation/verify
  is done by the user (or after reconnecting).

## Risks & rollback

- **Biggest risk:** the UI↔service refactor is large and only fully verifiable
  on-device. Mitigation: Stage 0 spike first; keep stages small and pushable.
- **Service plumbing is fiddly** (class name, foreground behavior, oscpy under
  p4a). Mitigation: the Stage 0 spike de-risks all of it before the refactor.
- **Rollback:** all work lands on a feature branch; if a stage misbehaves
  on-device it can be reverted without affecting the proven `main` build. The
  desktop app is untouched throughout (this is Android-only).
