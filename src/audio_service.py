"""
audio_service.py - Android background-playback foreground service.

Entry point for the foreground service declared in buildozer.spec
(``services = audioplayback:audio_service.py:foreground``). It runs in a
separate process from the UI, so it owns the actual audio engine
(``android.media.MediaPlayer`` via pyjnius) and survives the UI being
backgrounded or killed.

Protocol (see service_ipc): the UI sends JSON commands on ``ADDR_CMD`` to this
process's OSC server (``SERVICE_PORT``); this process pushes JSON state
snapshots on ``ADDR_STATE`` to the UI's OSC server (``UI_PORT``). All audio
runs here; the UI only sends commands and renders the pushed state.

This module is Android-only (jnius / oscpy / Android APIs) and is never
imported on the desktop. The pure wire format lives in service_ipc, which is
unit-tested separately.
"""

import time
import traceback

from jnius import autoclass, PythonJavaClass, java_method
from oscpy.client import OSCClient
from oscpy.server import OSCThreadServer

import service_ipc as ipc

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


class _OnComplete(PythonJavaClass):
    """Bridge android MediaPlayer.OnCompletionListener back to Python."""

    __javainterfaces__ = ["android/media/MediaPlayer$OnCompletionListener"]

    def __init__(self, callback):
        """Store the Python *callback* to run when a track finishes."""
        super().__init__()
        self._callback = callback

    @java_method("(Landroid/media/MediaPlayer;)V")
    def onCompletion(self, mp):
        """Invoked by Android on the service thread when playback completes."""
        try:
            self._callback()
        except Exception:
            traceback.print_exc()


class AudioService:
    """Owns the MediaPlayer, the foreground notification, and the OSC server."""

    def __init__(self):
        """Initialise empty state; the engine is created lazily per track."""
        self._service = PythonService.mService
        self._player = None
        self._on_complete = None      # keep a ref so jnius doesn't GC it
        self._path = ""
        self._title = ""
        self._subtitle = ""
        self._volume = 1.0
        self._ended_pending = False
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

    def play(self, path: str, title: str, subtitle: str) -> None:
        """Load *path* and start playing it, replacing any current track."""
        self._release()
        self._path, self._title, self._subtitle = path, title, subtitle
        self._ended_pending = False
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
            self._on_complete = _OnComplete(self._handle_completion)
            player.setOnCompletionListener(self._on_complete)
            player.start()
            self._player = player
            self._start_foreground(title, subtitle or "재생 중")
        except Exception:
            traceback.print_exc()
            self._release()
        self.push_state()

    def toggle(self) -> None:
        """Pause if playing, resume if paused."""
        player = self._player
        if player is None:
            return
        try:
            if player.isPlaying():
                player.pause()
            else:
                player.start()
        except Exception:
            traceback.print_exc()
        self.push_state()

    def pause(self) -> None:
        """Pause playback if a track is loaded and playing."""
        player = self._player
        if player is not None:
            try:
                if player.isPlaying():
                    player.pause()
            except Exception:
                traceback.print_exc()
        self.push_state()

    def resume(self) -> None:
        """Resume playback if a track is loaded and paused."""
        player = self._player
        if player is not None:
            try:
                player.start()
            except Exception:
                traceback.print_exc()
        self.push_state()

    def stop(self) -> None:
        """Stop playback and clear the current track."""
        self._release()
        self._path = self._title = self._subtitle = ""
        self._ended_pending = False
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

    def _handle_completion(self) -> None:
        """Mark the current track as ended and notify the UI once."""
        self._ended_pending = True
        self.push_state()

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
            ended=self._ended_pending,
        )
        try:
            self._client.send_message(ipc.ADDR_STATE, [payload.encode("utf-8")])
        except Exception:
            traceback.print_exc()
        # ``ended`` is a one-shot edge; clear it after reporting.
        if self._ended_pending:
            self._ended_pending = False

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
        if op == ipc.OP_PLAY:
            self.play(cmd.get("path", ""), cmd.get("title", ""),
                      cmd.get("subtitle", ""))
        elif op == ipc.OP_TOGGLE:
            self.toggle()
        elif op == ipc.OP_PAUSE:
            self.pause()
        elif op == ipc.OP_RESUME:
            self.resume()
        elif op == ipc.OP_STOP:
            self.stop()
        elif op == ipc.OP_SEEK:
            self.seek(float(cmd.get("position", 0.0)))
        elif op == ipc.OP_VOLUME:
            self.set_volume(float(cmd.get("volume", 1.0)))
        elif op == ipc.OP_PING:
            self.push_state()


def main() -> None:
    """Service entry point: set up OSC, then loop pushing state to the UI."""
    service = AudioService()
    try:
        server = OSCThreadServer()
        server.listen(address="127.0.0.1", port=ipc.SERVICE_PORT, default=True)
        server.bind(ipc.ADDR_CMD, service.handle_command)
        print("audio_service: listening on", ipc.SERVICE_PORT)
    except Exception:
        # A bind failure (e.g. port in use) must not crash the process: the
        # service has already entered the foreground, so keep it alive rather
        # than dying with an unhandled exception.
        traceback.print_exc()
    # Keep the process alive and push position updates while playing.
    while True:
        time.sleep(0.5)
        if service._is_playing():
            service.push_state()


if __name__ == "__main__":
    main()
