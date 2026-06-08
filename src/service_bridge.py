"""
service_bridge.py - UI-side bridge to the background-playback service.

Starts the Android foreground service (src/audio_service.py) and carries the
OSC traffic between the UI process and that service process: it sends JSON
commands to the service and forwards the service's JSON state snapshots to a
callback. Android-only — on the desktop (or if oscpy/jnius are unavailable, or
the service class is not found) ``start()`` returns False and the bridge stays
inert (``available`` is False), so the caller falls back to local playback.

Only the wire format (service_ipc) is unit-tested; this thin Android glue is
exercised on-device, like the rest of the Kivy UI.
"""

import traceback

import service_ipc as ipc


class ServiceBridge:
    """Owns the UI-side OSC client/server and starts the playback service."""

    def __init__(self, on_state):
        """
        Args:
            on_state: Callback invoked with a parsed state dict (see
                service_ipc.parse_state) whenever the service pushes a snapshot.
                It is called on the OSC server thread — the caller must marshal
                to the UI thread itself.
        """
        self.available = False
        self._on_state = on_state
        self._client = None
        self._server = None

    def start(self) -> bool:
        """
        Set up OSC and launch the foreground service.

        Returns:
            True if the service was started and OSC is wired; False off-device
            or on any failure (the caller should then use local playback).
        """
        try:
            from oscpy.client import OSCClient
            from oscpy.server import OSCThreadServer
            from jnius import autoclass

            self._server = OSCThreadServer()
            self._server.listen(address="127.0.0.1", port=ipc.UI_PORT,
                                default=True)
            self._server.bind(ipc.ADDR_STATE, self._handle_state)
            self._client = OSCClient("127.0.0.1", ipc.SERVICE_PORT)

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Service = autoclass("org.musiren.mp3archive.ServiceAudioplayback")
            Service.start(PythonActivity.mActivity, "")
            self.available = True
        except Exception:
            traceback.print_exc()
            self.available = False
        return self.available

    def send(self, op: str, **fields) -> None:
        """Send a command to the service (no-op if the bridge is inert)."""
        if not self.available or self._client is None:
            return
        try:
            payload = ipc.make_command(op, **fields).encode("utf-8")
            self._client.send_message(ipc.ADDR_CMD, [payload])
        except Exception:
            traceback.print_exc()

    def _handle_state(self, *values) -> None:
        """OSC handler: decode a state snapshot and hand it to the callback."""
        try:
            payload = values[0]
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode("utf-8")
            self._on_state(ipc.parse_state(payload))
        except Exception:
            traceback.print_exc()

    def stop_server(self) -> None:
        """Tear down the OSC server (best-effort)."""
        if self._server is not None:
            try:
                self._server.stop_all()
            except Exception:
                traceback.print_exc()
            self._server = None
