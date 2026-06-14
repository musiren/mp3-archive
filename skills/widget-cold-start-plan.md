# Plan: Widget Cold-Start Resume (Android)

## Request

Pressing the home-screen widget's transport buttons while the app is
closed does nothing. They must act on the saved 재생목록 state: resume the
saved track (toggle) or move within the saved queue (next/prev).

## Root cause

The widget buttons send implicit package broadcasts
(`org.musiren.mp3archive.TOGGLE/NEXT/PREV`). The only receiver for those
is registered **dynamically inside the service process**
(`audio_service._setup_controls`), so once the app/service process dies
the broadcasts have no receiver and the taps are silently dropped.

## Design

### Java: always-reachable static receiver

- New `WidgetActionReceiver` (manifest-declared via the existing
  `p4a_hooks.py` injection, `android:exported="false"`, **no intent
  filter** — explicit intents only, so the service's own implicit
  notification broadcasts are never double-handled).
- `PlayerWidgetProvider` button `PendingIntent`s now target that receiver
  explicitly (widget taps are exempt from the Android 12+
  background-FGS-start restriction).
- `onReceive`: if `ServiceAudioplayback` is running (own-service query via
  `ActivityManager.getRunningServices`), relay the action as the implicit
  package broadcast the service already listens for; otherwise cold-start
  the foreground service with the action string as the p4a
  `pythonServiceArgument`.

### Python service: restore the saved session on cold start

- `main()` reads `PYTHON_SERVICE_ARGUMENT` and hands a non-empty value to
  `AudioService.start_action(raw)`.
- `start_action`: map the raw action to TOGGLE/NEXT/PREV; when the queue
  is empty, restore the saved session first; then dispatch (toggle =
  play the saved index, seeking to the saved position; next/prev =
  advance/retreat from the saved index).
- Restore source: the queue items come from the shared
  `playback_queue.json` the UI already writes on every sync; the saved
  track/index/position/mode/seed come from the `app_state` table of the
  internal state DB (`<files dir>/mp3_archive.db`), opened read-only.
- New pure helpers in `service_ipc.py` so the logic is unit-testable
  off-device:
  - `read_resume_state(db_path)` → `{path,index,position,mode,seed}` with
    safe defaults (read-only sqlite; missing file/keys → defaults).
  - `resolve_resume_index(items, path, index)` → validated queue index
    (saved index if it still points at the saved path, else locate the
    path, else -1).

## Files

- `java/org/musiren/mp3archive/WidgetActionReceiver.java` — new.
- `java/org/musiren/mp3archive/PlayerWidgetProvider.java` — explicit
  intents.
- `p4a_hooks.py` — inject the second receiver (idempotent per receiver).
- `src/audio_service.py` — `start_action` + session restore glue.
- `src/service_ipc.py` — pure resume-state helpers.
- `test/test_service_ipc.py` — tests for the new helpers.

## Verification

- `python -m unittest discover -s test -v` before commit.
- On-device: kill the app (swipe away), tap widget play → saved track
  resumes at its position; next/prev move within the saved queue and
  respect shuffle order.
