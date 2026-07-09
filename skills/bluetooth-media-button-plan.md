# Plan: Bluetooth / Headset Media-Button Resume (Android)

## Request

On the app the user had before, pressing the Bluetooth earphone's play
button after a phone reboot (BT connect → play) started playback. This
app does nothing in that case.

## Root cause

Hardware media buttons (BT AVRCP / headset) reach an app only through
either (a) an **active `MediaSession`**, or (b) a **manifest-declared
receiver with an `android.intent.action.MEDIA_BUTTON` intent filter**
that the session's media-button `PendingIntent` points at. This app
creates its `MediaSession` only inside the running service process
(`audio_service._setup_controls`) and never calls
`setMediaButtonReceiver`, and there is no manifest MEDIA_BUTTON receiver.
So after a reboot — no process, no session — a media button has nowhere
to go and is dropped.

The widget cold-start added earlier does NOT cover this: it handles the
widget's own explicit-intent buttons, a different path from the system's
media-button routing.

## Design (mirrors the widget cold-start)

### Shared launcher (Java)
- New `PlaybackLauncher` with the exact relay-or-cold-start logic
  currently inline in `WidgetActionReceiver`:
  `dispatch(ctx, action)` → relay the package broadcast when the service
  runs, else start it as a foreground service with the action argument.
- `WidgetActionReceiver` delegates to it (behaviour unchanged), so the
  two entry points stay identical.

### Media-button receiver (Java)
- New `MediaButtonReceiver`, manifest-declared **with** the MEDIA_BUTTON
  intent filter (unlike the widget receiver — this system action is one
  the app never broadcasts internally, so no double-handling risk). It
  reads `Intent.EXTRA_KEY_EVENT`, maps the keycode
  (PLAY/PAUSE/PLAY_PAUSE/HEADSETHOOK → TOGGLE, NEXT, PREVIOUS, STOP), and
  calls `PlaybackLauncher.dispatch`. Only ACTION_DOWN is acted on (a
  press fires DOWN+UP).

### Session wiring (Python)
- In `_setup_controls`, after creating the session, call
  `setMediaButtonReceiver` with a broadcast `PendingIntent` to
  `MediaButtonReceiver` (guarded by API level; best-effort). This makes
  the framework route media buttons to our manifest receiver whenever the
  session is not active — including after the process dies.

### Manifest
- `p4a_hooks.RECEIVERS` gains `MediaButtonReceiver` with the MEDIA_BUTTON
  intent filter (idempotent per receiver, like the others).

### Cold-start dispatch (Python)
- `start_action` already maps the trailing `.TOGGLE/.NEXT/.PREV` and
  restores the saved session, so media buttons reuse it unchanged. STOP
  is ignored there (stopping a just-started idle service is a no-op).

## Files
- `java/.../PlaybackLauncher.java` — new shared launcher.
- `java/.../WidgetActionReceiver.java` — delegate to it.
- `java/.../MediaButtonReceiver.java` — new.
- `p4a_hooks.py` — inject the MEDIA_BUTTON receiver.
- `src/audio_service.py` — `setMediaButtonReceiver` wiring.

## Verification
- `python -m unittest discover -s test -v` (Python unchanged in logic; run
  to be safe).
- On-device (the real test — the Kivy/Java paths are device-only):
  reboot phone, connect BT earphones, press play → saved 재생목록 resumes;
  next/prev move within it; running-app case still single-toggles.

## Caveat
Exact post-reboot routing is Android-version-dependent; the manifest
MEDIA_BUTTON receiver plus `setMediaButtonReceiver` is the standard
robust approach, but it must be confirmed on the device.
