"""
service_ipc.py - Pure (de)serialisation for the UI <-> audio-service IPC.

The Android background-playback service runs in a separate process and talks to
the UI over OSC (oscpy). To keep the wire format simple and robust, every
message carries a single JSON string payload: commands on ``ADDR_CMD`` (UI ->
service) and state snapshots on ``ADDR_STATE`` (service -> UI). This module owns
that encoding plus the value normalisation (volume/seek clamping, op
validation, state defaults) so the logic is testable without Kivy, jnius, or a
device.
"""

import json

# OSC addresses (bytes, as oscpy expects).
ADDR_CMD = b"/cmd"      # UI -> service
ADDR_STATE = b"/state"  # service -> UI

# Fixed localhost ports the two processes agree on. The service listens for
# commands on SERVICE_PORT; the UI listens for state snapshots on UI_PORT.
SERVICE_PORT = 38291
UI_PORT = 38292

# Command ops (UI -> service).
OP_PLAY = "play"        # fields: path, title, subtitle
OP_TOGGLE = "toggle"    # play/pause flip
OP_PAUSE = "pause"
OP_RESUME = "resume"
OP_STOP = "stop"
OP_SEEK = "seek"        # field: position (seconds)
OP_VOLUME = "volume"    # field: volume (0.0..1.0)
OP_PING = "ping"

_OPS = frozenset({
    OP_PLAY, OP_TOGGLE, OP_PAUSE, OP_RESUME, OP_STOP, OP_SEEK, OP_VOLUME, OP_PING,
})


def _clamp01(value) -> float:
    """Clamp *value* to the inclusive range [0.0, 1.0]; non-numeric -> 0.0."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _non_negative(value) -> float:
    """Return float(*value*) clamped to >= 0.0; non-numeric -> 0.0."""
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def make_command(op: str, **fields) -> str:
    """
    Build a JSON command payload for the service.

    Args:
        op:     One of the ``OP_*`` constants.
        fields: Op-specific fields (e.g. path/title/subtitle for play,
                position for seek, volume for volume). Values are normalised:
                volume is clamped to [0, 1] and seek position to >= 0.

    Returns:
        A JSON string suitable as the single OSC argument on ``ADDR_CMD``.

    Raises:
        ValueError: If *op* is not a known command.
    """
    if op not in _OPS:
        raise ValueError(f"unknown command op: {op!r}")
    payload = {"op": op}
    payload.update(fields)
    if op == OP_VOLUME:
        payload["volume"] = _clamp01(payload.get("volume", 1.0))
    if op == OP_SEEK:
        payload["position"] = _non_negative(payload.get("position", 0.0))
    return json.dumps(payload)


def parse_command(payload: str) -> dict:
    """
    Parse a JSON command payload produced by :func:`make_command`.

    Args:
        payload: The JSON string received on ``ADDR_CMD``.

    Returns:
        A dict with at least an ``"op"`` key plus any op-specific fields.

    Raises:
        ValueError: If the payload is not valid JSON, is not an object, or
            carries an unknown/missing op.
    """
    try:
        data = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid command JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("command payload must be a JSON object")
    op = data.get("op")
    if op not in _OPS:
        raise ValueError(f"unknown command op: {op!r}")
    return data


def make_state(*, playing: bool, path: str = "", title: str = "",
               subtitle: str = "", position: float = 0.0, length: float = 0.0,
               ended: bool = False) -> str:
    """
    Build a JSON state snapshot for the UI.

    Args:
        playing:  True while audio is actively playing (not paused/stopped).
        path:     Absolute path of the current track ("" when idle).
        title:    Primary label (typically the filename).
        subtitle: Secondary label ("artist — title").
        position: Current playback position in seconds.
        length:   Track duration in seconds (0 if unknown).
        ended:    True for the one snapshot that reports a natural track end.

    Returns:
        A JSON string suitable as the single OSC argument on ``ADDR_STATE``.
    """
    return json.dumps({
        "playing": bool(playing),
        "path": path or "",
        "title": title or "",
        "subtitle": subtitle or "",
        "position": _non_negative(position),
        "length": _non_negative(length),
        "ended": bool(ended),
    })


def parse_state(payload: str) -> dict:
    """
    Parse a JSON state snapshot, filling defaults for any missing field.

    Args:
        payload: The JSON string received on ``ADDR_STATE``.

    Returns:
        A dict with keys playing, path, title, subtitle, position, length,
        ended — always present and of the right type, even if *payload* was
        malformed (in which case an idle/empty state is returned).
    """
    try:
        data = json.loads(payload)
        if not isinstance(data, dict):
            data = {}
    except (TypeError, ValueError):
        data = {}
    return {
        "playing": bool(data.get("playing", False)),
        "path": data.get("path", "") or "",
        "title": data.get("title", "") or "",
        "subtitle": data.get("subtitle", "") or "",
        "position": _non_negative(data.get("position", 0.0)),
        "length": _non_negative(data.get("length", 0.0)),
        "ended": bool(data.get("ended", False)),
    }
