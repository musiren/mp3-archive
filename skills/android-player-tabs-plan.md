# Android: Split List Management and Playback into Tabs

## Goal

On Android, separate the two concerns of the app into bottom-navigation tabs:

1. **목록 (List)** — DB-backed library management: scan a storage directory,
   browse stored records, select rows, and delete them.
2. **재생 (Player)** — play a selected track with play/pause and stop controls
   plus a position indicator.

The desktop (PyQt6) app already has rich playback (`QMediaPlayer`, playlist,
seek, prev/next). The Android app (`main_window_android.py`, KivyMD) had no
playback at all. This change adds a focused player and the tab split.

## UI structure (KV)

```
MDBoxLayout (root, vertical)
├── MDTopAppBar            # folder-search + delete actions (operate on the list)
└── MDBottomNavigation (id: bottom_nav)
    ├── MDBottomNavigationItem name="list"  text="목록"  icon="format-list-bulleted"
    │   └── MDProgressBar (scan) + MDLabel (status) + ScrollView>MDList (id: mp3_list)
    └── MDBottomNavigationItem name="player" text="재생" icon="play-circle"
        └── now_playing / now_playing_sub labels
            position_bar (MDProgressBar) + pos_label / dur_label
            play_button (MDIconButton) + stop button
```

## Interaction model

- **Tap a row body** → play that track and switch to the 재생 tab
  (`play_row` → `_play` → `bottom_nav.switch_tab("player")`).
- **Tap the row's right icon** → toggle selection for deletion
  (`toggle_select`, unchanged). This separates "play" from "select" cleanly.

## Playback engine

Uses `kivy.core.audio.SoundLoader` (auto-selects the Android `audio_android`
MediaPlayer provider on device, which decodes MP3 natively — no extra buildozer
requirement). Position/duration are polled with `Clock.schedule_interval`
every 0.5 s and shown via `position_bar` + `m:ss` time labels.

Pause/resume: Kivy `Sound` has no pause, so pause = remember `get_pos()` +
`stop()`; resume = `play()` + `seek(saved_pos)`. Natural end is detected when
`sound.state != "play"` during a poll, which resets the controls.

All audio calls are guarded; on load failure a Snackbar explains the file
cannot be played.

## Methods added

`play_row`, `_play`, `toggle_play_pause`, `stop_playback`, `_stop_sound`,
`_schedule_pos`, `_unschedule_pos`, `_update_position`, and the pure static
`_format_time`. `__init__` gains player state; `on_stop` stops the sound.

## Tests

- `_format_time` — pure, multiple cases (gated behind kivy presence like the
  rest of the module; verified in isolation locally since kivy cannot be
  installed on the host Python 3.14).
- KV id presence — extended to assert `bottom_nav`, `now_playing`,
  `position_bar`, `play_button` exist after `Builder.load_string`.

## Known risks / follow-ups

- MP3 playback depends on the `audio_android` provider being selected on the
  device. If a track fails to load, fall back to `ffpyplayer` (extra buildozer
  requirement) or a direct `pyjnius` MediaPlayer wrapper.
- No seek-by-drag yet (read-only position bar). Seeking and prev/next/auto-
  advance are deferred to a later iteration.
