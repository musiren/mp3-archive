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

from jnius import autoclass
from oscpy.client import OSCClient
from oscpy.server import OSCThreadServer

import service_ipc as ipc
from playlist import PLAY_MODES, next_index

# --- Android classes -------------------------------------------------------
PythonService = autoclass("org.kivy.android.PythonService")
MediaPlayer = autoclass("android.media.MediaPlayer")
AudioManager = autoclass("android.media.AudioManager")
PowerManager = autoclass("android.os.PowerManager")
Context = autoclass("android.content.Context")
NotificationBuilder = autoclass("android.app.Notification$Builder")
NotificationManager = autoclass("android.app.NotificationManager")
NotificationChannel = autoclass("android.app.NotificationChannel")
VERSION = autoclass("android.os.Build$VERSION")
Intent = autoclass("android.content.Intent")
PendingIntent = autoclass("android.app.PendingIntent")
PythonActivity = autoclass("org.kivy.android.PythonActivity")

CHANNEL_ID = "mp3archive_playback"
NOTIFICATION_ID = 0x4D5033  # non-zero ("MP3")


class AudioService:
    """Owns the queue, the MediaPlayer, the notification, and the OSC server."""

    def __init__(self):
        """Initialise empty state; the engine is created lazily per track."""
        self._service = PythonService.mService
        self._player = None
        self._items = []              # queue: list of {path,title,subtitle}
        self._index = -1              # current index into _items
        self._mode = PLAY_MODES[0]
        self._path = ""               # currently-loaded track path
        self._title = ""
        self._subtitle = ""
        self._volume = 1.0
        self._paused = False          # True while the user has paused
        self._was_playing = False     # True since play() until end/stop
        self._client = OSCClient("127.0.0.1", ipc.UI_PORT)
        self._start_foreground("준비 완료", "재생할 곡을 선택하세요")

    # -- foreground notification --------------------------------------------
    def _start_foreground(self, title: str, text: str) -> None:
        """Build/refresh the ongoing notification and enter the foreground."""
        try:
            service = self._service
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
            try:
                intent = Intent(service, PythonActivity)
                flags = 0x10000000 | 0x04000000  # NEW_TASK | CLEAR_TOP
                intent.setFlags(flags)
                pi_flag = 0x04000000 if VERSION.SDK_INT >= 31 else 0  # IMMUTABLE
                pi = PendingIntent.getActivity(service, 0, intent, pi_flag)
                builder.setContentIntent(pi)
            except Exception:
                traceback.print_exc()
            service.startForeground(NOTIFICATION_ID, builder.build())
        except Exception:
            traceback.print_exc()

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
            player.setVolume(self._volume, self._volume)
            player.start()
            self._player = player
            self._was_playing = True
            self._start_foreground(title or "재생 중", subtitle or "")
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
            else:
                player.start()
                self._paused = False
                self._was_playing = True
        except Exception:
            traceback.print_exc()
        self.push_state()

    def stop(self) -> None:
        """Stop playback and clear the current track (the queue is kept)."""
        self._release()
        self._path = self._title = self._subtitle = ""
        self._index = -1
        self._paused = False
        self._was_playing = False
        self._start_foreground("준비 완료", "재생할 곡을 선택하세요")
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
        player = self._player   # read once; a command thread may swap it
        if player is not None:
            try:
                player.setVolume(self._volume, self._volume)
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
