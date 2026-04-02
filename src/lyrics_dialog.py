"""
lyrics_dialog.py - Dialog that displays embedded lyrics for an audio file.

Reads lyrics from the file via mutagen and shows them in a scrollable
read-only text area.  Supports ID3 USLT frames (MP3), Vorbis LYRICS
comments (FLAC/OGG), and MP4/M4A ©lyr atoms.

Usage:
    dlg = LyricsDialog(file_info, parent=self)
    dlg.exec()
"""

from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from mutagen import File as MutagenFile


def _get_lyrics(path: str) -> str | None:
    """
    Extract embedded lyrics text from an audio file.

    Checks in order:
      1. EasyTag 'lyrics' key (FLAC, OGG, and some MP3 via EasyID3)
      2. ID3 USLT frames (MP3 / AIFF)
      3. MP4/M4A ©lyr atom

    Args:
        path: Absolute path to the audio file.

    Returns:
        The lyrics string, or None if none are found.
    """
    if not path:
        return None
    try:
        # EasyTag interface covers FLAC, OGG and MP3 with EasyID3 'lyrics'
        audio_easy = MutagenFile(path, easy=True)
        if audio_easy and audio_easy.tags:
            for key in ("lyrics", "LYRICS"):
                if key in audio_easy.tags:
                    val = audio_easy.tags[key]
                    return val[0] if isinstance(val, list) else str(val)

        # Raw tags: ID3 USLT frames and MP4 ©lyr
        audio_raw = MutagenFile(path, easy=False)
        if audio_raw and audio_raw.tags:
            # ID3: USLT::<lang> frames
            for key in list(audio_raw.tags.keys()):
                if key.startswith("USLT"):
                    return audio_raw.tags[key].text
            # MP4/M4A
            if "\xa9lyr" in audio_raw.tags:
                val = audio_raw.tags["\xa9lyr"]
                return val[0] if isinstance(val, list) else str(val)
    except Exception:
        pass
    return None


class LyricsDialog(QDialog):
    """
    Read-only dialog that shows the lyrics embedded in an audio file.

    Displays the track title and artist at the top, followed by the
    full lyrics text in a scrollable text area.  When no lyrics are
    found a short notice is shown instead.
    """

    def __init__(self, file_info: dict, parent=None) -> None:
        """
        Args:
            file_info: Row dict as returned by Mp3Manager.list_files() or
                       Mp3Manager.get_by_path().  Must contain at least 'path'.
            parent:    Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("가사")
        self.resize(500, 600)
        self._build_ui(file_info)

    def _build_ui(self, info: dict) -> None:
        """Create and arrange all child widgets."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title  = info.get("title")  or info.get("filename", "-")
        artist = info.get("artist") or "-"
        layout.addWidget(QLabel(f"<b>{title}</b>"))
        layout.addWidget(QLabel(f"아티스트: {artist}"))

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)

        lyrics = _get_lyrics(info.get("path", ""))
        text_edit.setPlainText(lyrics if lyrics else "(가사 정보가 없습니다)")

        layout.addWidget(text_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)
