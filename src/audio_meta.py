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
