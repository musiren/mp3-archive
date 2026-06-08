"""
audio_service.py - Android background-playback foreground service.

Entry point for the foreground service declared in buildozer.spec
(``services = audioplayback:audio_service.py:foreground``). It runs in a
separate process from the UI, so it owns the actual audio engine
(``android.media.MediaPlayer`` via pyjnius) AND, since Stage 1, the play queue
itself — so playback and auto-advance survive the UI being backgrounded or
killed.

Protocol (see service_ipc): the UI sends JSON commands on ``ADDR_CMD`` to this
process's OSC server (``SERVICE_PORT``); this process pushes JSON state
snapshots on ``ADDR_STATE`` to the UI's OSC server (``UI_PORT``). The UI sends
a ``sync`` command with the whole queue + desired index + play mode; the
service plays it and, when a track ends, advances on its own using the shared
``playlist`` logic.

This module is Android-only (jnius / oscpy / Android APIs) and is never
imported on the desktop. The pure wire format (service_ipc) and queue logic
(playlist) are unit-tested separately.

Note: track completion is detected by polling MediaPlayer.isPlaying() in
tick(), NOT via an OnCompletionListener. Implementing a Java interface from
Python (jnius PythonJavaClass) needs org.jnius.NativeInvocationHandler, which
is not on the classloader of a python-for-android *service* process, so
creating such a proxy throws ClassNotFoundException. Polling avoids any proxy.
"""

import time
import traceback

from jnius import autoclass, cast, java_method, PythonJavaClass
from oscpy.client import OSCClient
from oscpy.server import OSCThreadServer

import service_ipc as ipc
from playlist import PLAY_MODES, next_index, prev_index

# --- Android classes -------------------------------------------------------
PythonService = autoclass("org.kivy.android.PythonService")
MediaPlayer = autoclass("android.media.MediaPlayer")
AudioManager = autoclass("android.media.AudioManager")
AudioAttributes = autoclass("android.media.AudioAttributes")
AudioAttributesBuilder = autoclass("android.media.AudioAttributes$Builder")
AudioFocusRequestBuilder = autoclass("android.media.AudioFocusRequest$Builder")
PowerManager = autoclass("android.os.PowerManager")
Context = autoclass("android.content.Context")
Thread = autoclass("java.lang.Thread")
NotificationBuilder = autoclass("android.app.Notification$Builder")
NotificationManager = autoclass("android.app.NotificationManager")
NotificationChannel = autoclass("android.app.NotificationChannel")
MediaStyle = autoclass("android.app.Notification$MediaStyle")
MediaSession = autoclass("android.media.session.MediaSession")
PlaybackStateBuilder = autoclass("android.media.session.PlaybackState$Builder")
PlaybackState = autoclass("android.media.session.PlaybackState")
MediaMetadataBuilder = autoclass("android.media.MediaMetadata$Builder")
MediaMetadata = autoclass("android.media.MediaMetadata")
RDrawable = autoclass("android.R$drawable")
VERSION = autoclass("android.os.Build$VERSION")
Intent = autoclass("android.content.Intent")
PendingIntent = autoclass("android.app.PendingIntent")
PythonActivity = autoclass("org.kivy.android.PythonActivity")

CHANNEL_ID = "mp3archive_playback"
NOTIFICATION_ID = 0x4D5033  # non-zero ("MP3")

# Duck volume multiplier while another app holds transient focus (e.g. nav).
_DUCK_FACTOR = 0.2

# Notification / lock-screen control actions (broadcast back to the service).
_PKG = "org.musiren.mp3archive"
ACTION_TOGGLE = _PKG + ".TOGGLE"
ACTION_NEXT = _PKG + ".NEXT"
ACTION_PREV = _PKG + ".PREV"
ACTION_STOP = _PKG + ".STOP"
_PI_FLAGS = (0x08000000 | (0x04000000 if VERSION.SDK_INT >= 31 else 0))  # UPDATE|IMMUTABLE


def _install_service_classloader() -> None:
    """
    Make jnius Java-interface proxies resolvable in this service process.

    Implementing a Java interface from Python (PythonJavaClass) needs
    org.jnius.NativeInvocationHandler, which a service process's *system*
    classloader cannot see. Pin the service's app/dex classloader onto the
    current thread and eagerly cache the helper class, so later proxies built
    with ``__javacontext__ = 'app'`` resolve. Must run before any proxy is
    instantiated (the classloader is resolved at proxy-construction time).
    """
    try:
        service = PythonService.mService
        Thread.currentThread().setContextClassLoader(service.getClassLoader())
        autoclass("org.jnius.NativeInvocationHandler")
    except Exception:
        traceback.print_exc()


class _FocusListener(PythonJavaClass):
    """Bridge AudioManager.OnAudioFocusChangeListener back to Python."""

    __javainterfaces__ = ["android/media/AudioManager$OnAudioFocusChangeListener"]
    __javacontext__ = "app"   # resolve via the thread context (app) classloader

    def __init__(self, callback):
        """Store the Python *callback(focus_change_int)*."""
        super().__init__()
        self._callback = callback

    @java_method("(I)V")
    def onAudioFocusChange(self, focus_change):
        """Invoked by Android when audio focus changes."""
        try:
            self._callback(focus_change)
        except Exception:
            traceback.print_exc()


class AudioService:
    """Owns the queue, the MediaPlayer, the notification, and the OSC server."""

    def __init__(self):
        """Initialise empty state; the engine is created lazily per track."""
        _install_service_classloader()   # before any PythonJavaClass proxy
        self._service = PythonService.mService
        self._player = None
        self._items = []              # queue: list of {path,title,subtitle}
        self._index = -1              # current index into _items
        self._mode = PLAY_MODES[0]
        self._path = ""               # currently-loaded track path
        self._title = ""
        self._subtitle = ""
        self._volume = 1.0
        self._paused = False          # True while paused (user or focus loss)
        self._auto_paused = False     # True when paused by transient focus loss
        self._ducked = False          # True while ducked for transient focus
        self._was_playing = False     # True since play() until end/stop
        self._focus_listener = None
        self._focus_request = None    # AudioFocusRequest (API 26+)
        self._session = None          # MediaSession for lock-screen controls
        self._receiver = None         # BroadcastReceiver for notification taps
        self._client = OSCClient("127.0.0.1", ipc.UI_PORT)
        self._setup_controls()
        self._post_notification()

    # -- media controls (notification + lock screen) -------------------------
    def _setup_controls(self) -> None:
        """Create the MediaSession and register the control BroadcastReceiver."""
        try:
            self._session = MediaSession(self._service, "mp3archive")
            self._session.setActive(True)
        except Exception:
            traceback.print_exc()
            self._session = None
        try:
            from android.broadcast import BroadcastReceiver
            self._receiver = BroadcastReceiver(
                self._on_action,
                actions=[ACTION_TOGGLE, ACTION_NEXT, ACTION_PREV, ACTION_STOP])
            self._receiver.start()
        except Exception:
            traceback.print_exc()
            self._receiver = None

    def _on_action(self, context, intent) -> None:
        """Handle a control broadcast from a notification / lock-screen button."""
        try:
            action = intent.getAction()
        except Exception:
            return
        if action == ACTION_TOGGLE:
            self.toggle()
        elif action == ACTION_NEXT:
            self.play_next()
        elif action == ACTION_PREV:
            self.play_prev()
        elif action == ACTION_STOP:
            self.stop()

    def _action_pi(self, action: str, request_code: int):
        """Build a broadcast PendingIntent carrying *action* back to us."""
        intent = Intent(action)
        intent.setPackage(_PKG)
        return PendingIntent.getBroadcast(self._service, request_code, intent,
                                          _PI_FLAGS)

    def _content_pi(self):
        """Build the tap-to-open-app PendingIntent (or None on failure)."""
        try:
            intent = Intent(self._service, PythonActivity)
            intent.setFlags(0x10000000 | 0x04000000)  # NEW_TASK | CLEAR_TOP
            flag = 0x04000000 if VERSION.SDK_INT >= 31 else 0  # IMMUTABLE
            return PendingIntent.getActivity(self._service, 0, intent, flag)
        except Exception:
            traceback.print_exc()
            return None

    def _update_session(self) -> None:
        """Push current metadata + playback state to the MediaSession."""
        session = self._session
        if session is None:
            return
        try:
            meta = (MediaMetadataBuilder()
                    .putString(MediaMetadata.METADATA_KEY_TITLE,
                               self._subtitle or self._title or "")
                    .putString(MediaMetadata.METADATA_KEY_ARTIST,
                               self._title or "")
                    .build())
            session.setMetadata(meta)
            pos, _ = self._position_length()
            playing = self._is_playing()
            actions = (PlaybackState.ACTION_PLAY_PAUSE
                       | PlaybackState.ACTION_PLAY | PlaybackState.ACTION_PAUSE
                       | PlaybackState.ACTION_SKIP_TO_NEXT
                       | PlaybackState.ACTION_SKIP_TO_PREVIOUS
                       | PlaybackState.ACTION_STOP)
            st = (PlaybackState.STATE_PLAYING if playing
                  else PlaybackState.STATE_PAUSED)
            state = (PlaybackStateBuilder()
                     .setActions(actions)
                     .setState(st, int(pos * 1000), 1.0)
                     .build())
            session.setPlaybackState(state)
        except Exception:
            traceback.print_exc()

    def _post_notification(self) -> None:
        """Build the ongoing media notification and (re-)enter the foreground."""
        try:
            service = self._service
            title = self._title or "준비 완료"
            text = self._subtitle or ("재생 중" if self._path
                                      else "재생할 곡을 선택하세요")
            playing = self._is_playing()
            if VERSION.SDK_INT >= 26:
                channel = NotificationChannel(
                    CHANNEL_ID, "재생", NotificationManager.IMPORTANCE_LOW)
                nm = service.getSystemService(Context.NOTIFICATION_SERVICE)
                nm.createNotificationChannel(channel)
                builder = NotificationBuilder(service, CHANNEL_ID)
            else:
                builder = NotificationBuilder(service)
            builder.setContentTitle(title)
            builder.setContentText(text)
            builder.setOngoing(True)
            builder.setSmallIcon(service.getApplicationInfo().icon)
            builder.setVisibility(1)   # Notification.VISIBILITY_PUBLIC
            content = self._content_pi()
            if content is not None:
                builder.setContentIntent(content)
            # Transport actions: prev / play-pause / next / stop.
            try:
                builder.addAction(RDrawable.ic_media_previous, "이전",
                                  self._action_pi(ACTION_PREV, 1))
                builder.addAction(
                    RDrawable.ic_media_pause if playing
                    else RDrawable.ic_media_play,
                    "일시정지" if playing else "재생",
                    self._action_pi(ACTION_TOGGLE, 2))
                builder.addAction(RDrawable.ic_media_next, "다음",
                                  self._action_pi(ACTION_NEXT, 3))
                builder.addAction(RDrawable.ic_menu_close_clear_cancel, "정지",
                                  self._action_pi(ACTION_STOP, 4))
                style = MediaStyle().setShowActionsInCompactView(0, 1, 2)
                if self._session is not None:
                    style = style.setMediaSession(self._session.getSessionToken())
                builder.setStyle(style)
            except Exception:
                traceback.print_exc()
            service.startForeground(NOTIFICATION_ID, builder.build())
        except Exception:
            traceback.print_exc()

    def _refresh_controls(self) -> None:
        """Refresh the MediaSession state and the ongoing notification."""
        self._update_session()
        self._post_notification()

    # -- playback engine -----------------------------------------------------
    def _release(self) -> None:
        """Release the current MediaPlayer if any (idempotent)."""
        if self._player is not None:
            try:
                self._player.release()
            except Exception:
                traceback.print_exc()
            self._player = None

    def _play_path(self, path: str, title: str, subtitle: str) -> None:
        """Load *path* and start playing it, replacing any current track."""
        self._release()
        self._path, self._title, self._subtitle = path, title, subtitle
        self._paused = False
        self._was_playing = False
        try:
            player = MediaPlayer()
            player.setAudioStreamType(AudioManager.STREAM_MUSIC)
            try:
                player.setWakeMode(self._service, PowerManager.PARTIAL_WAKE_LOCK)
            except Exception:
                traceback.print_exc()
            player.setDataSource(path)
            player.prepare()
            self._player = player
            self._ducked = False
            self._apply_player_volume()
            self._request_focus()
            player.start()
            self._was_playing = True
            self._refresh_controls()
        except Exception:
            traceback.print_exc()
            self._release()

    def _play_index(self, index: int) -> None:
        """Make queue item *index* current and start playing it."""
        if not (0 <= index < len(self._items)):
            return
        self._index = index
        item = self._items[index]
        self._play_path(item.get("path", ""), item.get("title", ""),
                        item.get("subtitle", ""))

    # -- commands ------------------------------------------------------------
    def sync(self, items: list, index: int, mode: str) -> None:
        """
        Replace the queue/mode and play *index* (the one sync command).

        - Empty queue: stop and go idle.
        - index in range and different from the currently-playing track:
          start playing it.
        - index in range but already the current track: keep playing, just
          adopt the updated queue/mode (e.g. the user appended songs).
        - index out of range (e.g. -1): keep current playback, adopt queue/mode.
        """
        self._items = items
        self._mode = mode if mode in PLAY_MODES else PLAY_MODES[0]
        # Re-derive the current index from the playing path so auto-advance
        # stays correct after the queue was edited (insert/remove shifts).
        if self._path:
            for i, it in enumerate(items):
                if it.get("path", "") == self._path:
                    self._index = i
                    break
        if not items:
            self._index = -1
            self.stop()
            return
        if 0 <= index < len(items):
            already = (self._player is not None
                       and items[index].get("path", "") == self._path)
            if already:
                self.push_state()   # already playing this track; keep going
            else:
                self._play_index(index)
        else:
            # index < 0 / out of range: keep current playback, queue updated.
            self.push_state()

    def toggle(self) -> None:
        """Pause if playing, resume if paused."""
        player = self._player
        if player is None:
            self.push_state()
            return
        try:
            if player.isPlaying():
                player.pause()
                self._paused = True
                self._auto_paused = False   # user action overrides focus pause
            else:
                self._request_focus()
                player.start()
                self._paused = False
                self._auto_paused = False
                self._was_playing = True
        except Exception:
            traceback.print_exc()
        self._refresh_controls()
        self.push_state()

    def pause(self) -> None:
        """Pause playback if currently playing (used by audio-focus loss)."""
        player = self._player
        if player is not None:
            try:
                if player.isPlaying():
                    player.pause()
                    self._paused = True
            except Exception:
                traceback.print_exc()
        self._refresh_controls()
        self.push_state()

    def resume(self) -> None:
        """Resume playback (used when transient audio focus is regained)."""
        player = self._player
        if player is not None:
            try:
                self._request_focus()
                player.start()
                self._paused = False
                self._was_playing = True
            except Exception:
                traceback.print_exc()
        self._refresh_controls()
        self.push_state()

    def play_next(self) -> None:
        """Skip to the next track per the play mode (notification/lock-screen)."""
        idx = next_index(self._index, len(self._items), self._mode, ended=False)
        if idx is not None and self._items:
            self._play_index(idx)
            self.push_state()

    def play_prev(self) -> None:
        """Skip to the previous track per the play mode."""
        idx = prev_index(self._index, len(self._items), self._mode)
        if idx is not None and self._items:
            self._play_index(idx)
            self.push_state()

    def stop(self) -> None:
        """Stop playback and clear the current track (the queue is kept)."""
        self._abandon_focus()
        self._release()
        self._path = self._title = self._subtitle = ""
        self._index = -1
        self._paused = False
        self._auto_paused = False
        self._ducked = False
        self._was_playing = False
        self._refresh_controls()
        self.push_state()

    def seek(self, position: float) -> None:
        """Seek to *position* seconds (best-effort)."""
        player = self._player
        if player is not None:
            try:
                player.seekTo(int(position * 1000))
            except Exception:
                traceback.print_exc()
        self.push_state()

    def set_volume(self, volume: float) -> None:
        """Set the playback volume (0.0..1.0), remembered across tracks."""
        self._volume = max(0.0, min(1.0, volume))
        self._apply_player_volume()

    # -- audio focus ---------------------------------------------------------
    def _audio_manager(self):
        """Return the system AudioManager."""
        return cast("android.media.AudioManager",
                    self._service.getSystemService(Context.AUDIO_SERVICE))

    def _apply_player_volume(self) -> None:
        """Apply the current volume to the player, accounting for ducking."""
        player = self._player   # read once; a command thread may swap it
        if player is None:
            return
        vol = self._volume * (_DUCK_FACTOR if self._ducked else 1.0)
        try:
            player.setVolume(vol, vol)
        except Exception:
            traceback.print_exc()

    def _request_focus(self) -> None:
        """Request audio focus so calls/other media pause us (best-effort)."""
        try:
            am = self._audio_manager()
            if self._focus_listener is None:
                self._focus_listener = _FocusListener(self._on_focus_change)
            if VERSION.SDK_INT >= 26:
                if self._focus_request is None:
                    attrs = (AudioAttributesBuilder()
                             .setUsage(AudioAttributes.USAGE_MEDIA)
                             .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC)
                             .build())
                    self._focus_request = (
                        AudioFocusRequestBuilder(AudioManager.AUDIOFOCUS_GAIN)
                        .setAudioAttributes(attrs)
                        .setOnAudioFocusChangeListener(self._focus_listener)
                        .build())
                am.requestAudioFocus(self._focus_request)
            else:
                am.requestAudioFocus(self._focus_listener,
                                     AudioManager.STREAM_MUSIC,
                                     AudioManager.AUDIOFOCUS_GAIN)
        except Exception:
            traceback.print_exc()

    def _abandon_focus(self) -> None:
        """Release audio focus (best-effort)."""
        try:
            am = self._audio_manager()
            if VERSION.SDK_INT >= 26 and self._focus_request is not None:
                am.abandonAudioFocusRequest(self._focus_request)
            elif self._focus_listener is not None:
                am.abandonAudioFocus(self._focus_listener)
        except Exception:
            traceback.print_exc()

    def _on_focus_change(self, change) -> None:
        """React to audio-focus changes (pause / duck / resume)."""
        try:
            if change == AudioManager.AUDIOFOCUS_LOSS:
                # Permanent loss (another media app): pause, don't auto-resume.
                self._ducked = False
                self._auto_paused = False
                self.pause()
            elif change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT:
                # Transient (call/notification): pause and resume on regain.
                self._ducked = False
                if self._is_playing():
                    self._auto_paused = True
                self.pause()
            elif change == AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK:
                self._ducked = True
                self._apply_player_volume()
            elif change == AudioManager.AUDIOFOCUS_GAIN:
                if self._ducked:
                    self._ducked = False
                    self._apply_player_volume()
                if self._auto_paused:
                    self._auto_paused = False
                    self.resume()
        except Exception:
            traceback.print_exc()

    def _advance_ended(self) -> None:
        """Auto-advance to the next track per the play mode, or stop."""
        idx = next_index(self._index, len(self._items), self._mode, ended=True)
        if idx is not None and self._items:
            self._play_index(idx)
            self.push_state()
        else:
            self.stop()

    # -- state push ----------------------------------------------------------
    def _position_length(self):
        """Return (position_sec, length_sec) from the player, or (0, 0)."""
        player = self._player
        if player is None:
            return 0.0, 0.0
        try:
            pos = max(0, player.getCurrentPosition()) / 1000.0
            length = max(0, player.getDuration()) / 1000.0
            return pos, length
        except Exception:
            return 0.0, 0.0

    def _is_playing(self) -> bool:
        """Return True only while the player is actively playing."""
        player = self._player
        if player is None:
            return False
        try:
            return bool(player.isPlaying())
        except Exception:
            return False

    def push_state(self) -> None:
        """Send a state snapshot to the UI's OSC server."""
        pos, length = self._position_length()
        payload = ipc.make_state(
            playing=self._is_playing(), path=self._path, title=self._title,
            subtitle=self._subtitle, position=pos, length=length,
            index=self._index,
        )
        try:
            self._client.send_message(ipc.ADDR_STATE, [payload.encode("utf-8")])
        except Exception:
            traceback.print_exc()

    def tick(self) -> None:
        """
        Periodic poll (~2x/sec): push position, detect end, auto-advance.

        Completion is detected by polling: once a track has started,
        MediaPlayer.isPlaying() going False while the user has not paused means
        the track finished, so advance to the next track (or stop) — this runs
        in the service, so it works even when the UI is backgrounded or gone.
        """
        player = self._player
        if player is None:
            return
        try:
            playing = bool(player.isPlaying())
        except Exception:
            playing = False
        if playing:
            self._was_playing = True
            self.push_state()
        elif self._was_playing and not self._paused:
            self._was_playing = False
            self._advance_ended()

    # -- command dispatch ----------------------------------------------------
    def handle_command(self, *values) -> None:
        """OSC handler: decode one JSON command and dispatch it."""
        try:
            payload = values[0]
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode("utf-8")
            cmd = ipc.parse_command(payload)
        except Exception:
            traceback.print_exc()
            return
        op = cmd.get("op")
        if op == ipc.OP_SYNC:
            self.sync(cmd.get("items", []), cmd.get("index", -1),
                      cmd.get("mode", PLAY_MODES[0]))
        elif op == ipc.OP_TOGGLE:
            self.toggle()
        elif op == ipc.OP_STOP:
            self.stop()
        elif op == ipc.OP_SEEK:
            self.seek(float(cmd.get("position", 0.0)))
        elif op == ipc.OP_VOLUME:
            self.set_volume(float(cmd.get("volume", 1.0)))
        elif op == ipc.OP_PING:
            self.push_state()


def main() -> None:
    """Service entry point: set up OSC, then loop ticking the player."""
    service = AudioService()
    try:
        server = OSCThreadServer()
        server.listen(address="127.0.0.1", port=ipc.SERVICE_PORT, default=True)
        server.bind(ipc.ADDR_CMD, service.handle_command)
        print("audio_service: listening on", ipc.SERVICE_PORT)
    except Exception:
        # A bind failure (e.g. port in use) must not crash the process: the
        # service has already entered the foreground, so keep it alive.
        traceback.print_exc()
    while True:
        time.sleep(0.5)
        service.tick()


if __name__ == "__main__":
    main()
