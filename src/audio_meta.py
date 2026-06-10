"""
audio_meta.py - GUI-independent audio metadata helpers (mutagen only).

Extracted so both the PyQt desktop UI and the Kivy Android UI can share the
same album-art / lyrics extraction and tag-mapping logic, and so the logic is
unit-testable without importing PyQt6 or Kivy.
"""

from mutagen import File as MutagenFile


def _has_hangul(text: str) -> bool:
    """Return True if the text contains any Korean (Hangul) characters."""
    return any(
        "가" <= ch <= "힣"     # Hangul syllables
        or "ᄀ" <= ch <= "ᇿ"  # Hangul Jamo
        or "㄰" <= ch <= "㆏"  # Hangul Compatibility Jamo
        for ch in text
    )


def fix_mojibake(text: str | None) -> str | None:
    """
    Repair Korean tag/lyrics text that was decoded from CP949 bytes as Latin-1.

    Older Korean MP3s store ID3 tags (and sometimes lyrics) in CP949/EUC-KR
    with no usable encoding flag, so mutagen decodes them as Latin-1 and yields
    mojibake such as '¾ÆÁÖ...'. If re-encoding the string to Latin-1 and
    decoding it as CP949 produces Hangul where there was none, return the
    repaired text; otherwise return the input unchanged so that correctly
    decoded Korean and genuine Latin text are left alone.

    Args:
        text: The (possibly mojibake) string, or None.

    Returns:
        The repaired Korean string, or the original text unchanged.
    """
    if not text or _has_hangul(text):
        return text
    try:
        repaired = text.encode("latin-1").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return repaired if _has_hangul(repaired) else text


def _clean_lyrics(text: str | None) -> str | None:
    """
    Repair encoding and normalise line endings for embedded lyrics.

    Lyrics frames frequently use CRLF or bare CR line endings; Kivy renders a
    stray carriage return as a tofu box at the end of every line, so collapse
    them to plain '\\n' (after the usual mojibake repair).

    Args:
        text: Raw lyrics string, or None.

    Returns:
        Cleaned lyrics, or None/empty unchanged.
    """
    text = fix_mojibake(text)
    if not text:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n")


def get_album_art(path: str) -> bytes | None:
    """
    Extract embedded album art from an audio file.

    Supports ID3 (APIC), FLAC/Ogg (pictures), and MP4/M4A (covr).

    Args:
        path: Absolute path to the audio file.

    Returns:
        Raw image bytes, or None if no art is found or the file is unreadable.
    """
    try:
        audio = MutagenFile(path)
        if audio is None:
            return None
        if audio.tags:
            for key in audio.tags.keys():
                if key.startswith("APIC"):
                    return audio.tags[key].data
        if hasattr(audio, "pictures") and audio.pictures:
            return audio.pictures[0].data
        if audio.tags and "covr" in audio.tags:
            return bytes(audio.tags["covr"][0])
    except Exception:
        pass
    return None


def get_album(path: str) -> str | None:
    """
    Read the album name embedded in an audio file.

    Args:
        path: Absolute path to the audio file.

    Returns:
        The (mojibake-repaired) album name, or None if absent or the file
        is unreadable.
    """
    try:
        audio = MutagenFile(path, easy=True)
        if audio is not None and audio.tags:
            val = audio.tags.get("album")
            text = val[0] if isinstance(val, list) and val else val
            if text:
                return fix_mojibake(str(text))
    except Exception:
        pass
    return None


def get_lyrics(path: str) -> str | None:
    """
    Extract embedded lyrics text from an audio file.

    Checks, in order: EasyTag 'lyrics' (FLAC/OGG/EasyID3), ID3 USLT frames
    (MP3/AIFF), and the MP4/M4A ``\\xa9lyr`` atom.

    Args:
        path: Absolute path to the audio file.

    Returns:
        The lyrics string, or None if none are found.
    """
    if not path:
        return None
    try:
        audio_easy = MutagenFile(path, easy=True)
        if audio_easy and audio_easy.tags:
            for key in ("lyrics", "LYRICS"):
                if key in audio_easy.tags:
                    val = audio_easy.tags[key]
                    return _clean_lyrics(val[0] if isinstance(val, list) else str(val))

        audio_raw = MutagenFile(path, easy=False)
        if audio_raw and audio_raw.tags:
            for key in list(audio_raw.tags.keys()):
                if key.startswith("USLT"):
                    return _clean_lyrics(audio_raw.tags[key].text)
            if "\xa9lyr" in audio_raw.tags:
                val = audio_raw.tags["\xa9lyr"]
                return val[0] if isinstance(val, list) else str(val)
    except Exception:
        pass
    return None


# Edit-form field name -> mutagen easy-tag key. 'year' maps to the easy 'date'
# key (the same convention Mp3Manager.update_tags uses for the DB 'year' column).
_FORM_TO_EASY = {
    "title":   "title",
    "artist":  "artist",
    "album":   "album",
    "genre":   "genre",
    "year":    "date",
    "comment": "comment",
}


# Human-readable Korean labels for normalised mutagen easy-tag keys, mirroring
# the desktop tag-detail dialog so both front-ends label tags identically.
_EASY_TAG_LABELS: dict[str, str] = {
    "title":        "제목",
    "artist":       "아티스트",
    "albumartist":  "앨범 아티스트",
    "album":        "앨범",
    "date":         "년도",
    "genre":        "장르",
    "tracknumber":  "트랙",
    "discnumber":   "디스크",
    "comment":      "코멘트",
    "composer":     "작곡가",
    "lyricist":     "작사가",
    "lyrics":       "가사",
    "copyright":    "저작권",
    "encodedby":    "인코더",
    "bpm":          "BPM",
    "isrc":         "ISRC",
    "language":     "언어",
    "organization": "레이블",
    "website":      "웹사이트",
}

# The easy-tag keys already exposed as dedicated fields in the edit form, so
# read_all_tags' callers can present the remaining tags separately.
STANDARD_EASY_KEYS = frozenset({"title", "artist", "album", "genre", "date",
                                "comment"})


def tag_display_label(key: str) -> str:
    """
    Return the Korean display label for a mutagen easy-tag key.

    Args:
        key: A lowercase easy-tag key (e.g. "albumartist").

    Returns:
        The mapped Korean label, or the key itself when it is unknown.
    """
    return _EASY_TAG_LABELS.get(key, key)


def read_all_tags(path: str) -> list:
    """
    Read every easy-tag key/value pair embedded in an audio file.

    Args:
        path: Absolute path to the audio file.

    Returns:
        A list of ``(label, key, value)`` tuples sorted by key, where *label*
        is the Korean display label, *key* is the mutagen easy-tag key, and
        *value* is the first (mojibake-repaired) string value. Empty when the
        file is unreadable or carries no tags.
    """
    rows = []
    try:
        audio = MutagenFile(path, easy=True)
        if audio is not None and audio.tags:
            for key in sorted(audio.tags.keys()):
                val = audio.tags.get(key)
                text = val[0] if isinstance(val, list) and val else str(val)
                rows.append((tag_display_label(key), key,
                             fix_mojibake(str(text)) or ""))
    except Exception:
        pass
    return rows


def get_stream_info(path: str) -> dict:
    """
    Read the audio stream properties of a file (sample rate, bitrate, etc.).

    Args:
        path: Absolute path to the audio file.

    Returns:
        A dict with any of the keys ``sample_rate``, ``channels``,
        ``bitrate`` (bits/s), and ``length`` (seconds) that mutagen exposes
        for the file. Empty when the file is unreadable or has no stream info.
    """
    stream = {}
    try:
        audio = MutagenFile(path)
        info = getattr(audio, "info", None)
        if info is not None:
            for attr in ("sample_rate", "channels", "bitrate", "length"):
                value = getattr(info, attr, None)
                if value:
                    stream[attr] = value
    except Exception:
        pass
    return stream


def _format_filesize(num) -> str:
    """Format a byte count as B / KB / MB (e.g. 1536 -> '1.5 KB'); '-' if unknown."""
    try:
        num = int(num)
    except (TypeError, ValueError):
        return "-"
    if num < 0:
        return "-"
    if num < 1024:
        return f"{num} B"
    if num < 1024 ** 2:
        return f"{num / 1024:.1f} KB"
    return f"{num / 1024 ** 2:.1f} MB"


def _format_seconds(seconds) -> str:
    """Format a duration in seconds as 'M:SS'; '-' when missing or non-positive."""
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return "-"
    if total <= 0:
        return "-"
    return f"{total // 60}:{total % 60:02d}"


def format_summary_rows(info: dict, stream: dict | None = None) -> list:
    """
    Build read-only (label, value) summary rows for a file-detail view.

    Combines the file-level facts stored in the DB row (size, duration,
    created/modified timestamps) with live stream properties read from the
    file, formatting each for display. Stream rows are omitted when the value
    is unavailable.

    Args:
        info:   A DB row dict (as from Mp3Manager.get_by_path) — uses
                ``filesize``, ``duration``, ``file_created_at``,
                ``file_modified_at``.
        stream: Optional stream dict from get_stream_info(); when omitted, only
                the file-level rows are produced.

    Returns:
        A list of ``(label, value)`` string tuples, ready to render.
    """
    info = info or {}
    stream = stream or {}
    rows = [
        ("크기", _format_filesize(info.get("filesize"))),
        ("길이", _format_seconds(info.get("duration") or stream.get("length"))),
        ("생성일시", info.get("file_created_at") or "-"),
        ("수정일시", info.get("file_modified_at") or "-"),
    ]
    if stream.get("sample_rate"):
        rows.append(("샘플레이트", f"{stream['sample_rate']} Hz"))
    if stream.get("channels"):
        rows.append(("채널", str(stream["channels"])))
    if stream.get("bitrate"):
        rows.append(("비트레이트", f"{stream['bitrate'] // 1000} kbps"))
    return rows


def to_easy_tags(form: dict) -> dict:
    """
    Map a tag-edit form dict to mutagen easy-tag keys, dropping blank values.

    Blank (empty/whitespace) values are omitted so they do not clobber existing
    tags; only fields the user actually filled in are written.

    Args:
        form: Mapping of form field names (title, artist, album, genre, year,
              comment) to their string values.

    Returns:
        A dict of easy-tag key -> stripped value, suitable for
        Mp3Manager.update_tags().
    """
    tags = {}
    for field, value in form.items():
        key = _FORM_TO_EASY.get(field)
        if key and value and value.strip():
            tags[key] = value.strip()
    return tags
