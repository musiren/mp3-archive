"""
tag_detail_dialog.py - Popup showing all metadata tags of an audio file.

Reads tags directly from the file via mutagen and displays every
key-value pair in a scrollable table, giving the user a full view
of what is embedded in the file.

Usage:
    dlg = TagDetailDialog(file_info, parent=self)
    dlg.exec()
"""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QFrame,
)

from mutagen import File as MutagenFile

# Human-readable Korean labels for normalised mutagen easy-tag keys.
_TAG_LABELS: dict[str, str] = {
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
    "replaygain_track_gain": "ReplayGain (트랙)",
    "replaygain_album_gain": "ReplayGain (앨범)",
}


def _get_album_art(path: str) -> bytes | None:
    """
    Extract embedded album art from an audio file.

    Supports ID3 (APIC), FLAC/Ogg (pictures), and MP4/M4A (covr).

    Args:
        path: Absolute path to the audio file.

    Returns:
        Raw image bytes, or None if no art is found.
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


class TagDetailDialog(QDialog):
    """
    Read-only dialog that shows every tag embedded in an audio file.

    Tag keys and values are read via mutagen and displayed in a two-column
    table (태그 / 값).  The dialog also shows a summary row (filename,
    format, duration, filesize) at the top.
    """

    def __init__(self, file_info: dict, manager=None, parent=None) -> None:
        """
        Args:
            file_info: Row dict as returned by Mp3Manager.list_files().
            manager:   Mp3Manager instance used to persist tag edits.
                       When None, the save button is hidden.
            parent:    Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("자세히 — 태그 정보")
        self.resize(680, 560)

        self._file_info = file_info
        self._manager   = manager
        # Maps table row index → easy-tag key for editable rows
        self._tag_keys: dict[int, str] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create and arrange all child widgets."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        info = self._file_info
        path = info.get("path", "")

        # Header: file info on the left, album art on the right
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        info_col.addWidget(QLabel(f"<b>파일:</b> {info.get('filename', '-')}"))
        info_col.addWidget(QLabel(f"<b>경로:</b> {path}"))
        info_col.addStretch()
        header_row.addLayout(info_col, stretch=1)

        self._art_label = QLabel("♪")
        self._art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._art_label.setFixedSize(140, 140)
        self._art_label.setStyleSheet(
            "QLabel { background: #e8e8e8; border: 1px solid #ccc; font-size: 32px; }"
        )
        art_bytes = _get_album_art(path)
        if art_bytes:
            pix = QPixmap()
            pix.loadFromData(art_bytes)
            self._art_label.setPixmap(
                pix.scaled(140, 140,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        header_row.addWidget(self._art_label)
        layout.addLayout(header_row)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # Tag table
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["태그", "값"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(True)
        layout.addWidget(self._table)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        self._btn_save  = QPushButton("저장")
        btn_close       = QPushButton("닫기")
        btn_row.addStretch()
        if self._manager:
            btn_row.addWidget(self._btn_save)
            self._btn_save.clicked.connect(self._on_save_clicked)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        btn_close.clicked.connect(self.accept)
        self._table.itemChanged.connect(self._on_item_changed)

        self._load_tags(path)

    def _on_item_changed(self, item) -> None:
        """Re-enable the save button when any editable cell is modified."""
        if self._manager and item.column() == 1:
            self._btn_save.setEnabled(True)
            self._status_label.setText("저장되지 않은 변경 사항이 있습니다.")

    def showEvent(self, event) -> None:
        """Set initial column widths to 30 / 70 % of the table width."""
        super().showEvent(event)
        total = self._table.viewport().width()
        self._table.setColumnWidth(0, int(total * 0.30))
        self._table.setColumnWidth(1, int(total * 0.70))

    def _on_save_clicked(self) -> None:
        """
        Collect edited tag values and write them to the file and DB.

        Only rows that have changed since the dialog was opened are written.
        Read-only rows (stream info, file summary) are ignored.
        """
        path = self._file_info.get("path", "")
        changed: dict[str, str] = {}
        for row, tag_key in self._tag_keys.items():
            item = self._table.item(row, 1)
            if item:
                changed[tag_key] = item.text()

        if not changed:
            self._status_label.setText("변경된 태그가 없습니다.")
            return

        try:
            self._manager.update_tags(path, changed)
            self._status_label.setText(f"{len(changed)}개 태그가 저장되었습니다.")
            self._btn_save.setEnabled(False)
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", str(e))

    # ------------------------------------------------------------------
    # Tag loading
    # ------------------------------------------------------------------

    def _load_tags(self, path: str) -> None:
        """
        Read all tags from the file and populate the table.

        Displays a set of standard summary fields first (format, duration,
        filesize, bitrate) followed by every tag key-value pair found by
        mutagen.

        Args:
            path: Absolute path to the audio file.
        """
        # Each row is (display_label, display_value, easy_tag_key_or_None)
        # easy_tag_key is None for read-only summary/stream rows.
        rows: list[tuple[str, str, str | None]] = []

        # --- File-level summary from DB (read-only) ---
        info = self._file_info
        rows.append(("크기",     f"{info.get('filesize', '-')} bytes", None))
        rows.append(("길이",     _fmt_duration(info.get("duration")),  None))
        rows.append(("생성일시", info.get("file_created_at") or "-",   None))
        rows.append(("수정일시", info.get("file_modified_at") or "-",  None))

        # --- Tags from file ---
        try:
            audio = MutagenFile(path, easy=True)
            if audio is None:
                self._status_label.setText("파일을 읽을 수 없습니다.")
            else:
                # Audio stream info (read-only)
                if hasattr(audio, "info"):
                    ai = audio.info
                    if hasattr(ai, "sample_rate"):
                        rows.append(("샘플레이트", f"{ai.sample_rate} Hz", None))
                    if hasattr(ai, "channels"):
                        rows.append(("채널", str(ai.channels), None))
                    if hasattr(ai, "bitrate"):
                        rows.append(("비트레이트", f"{ai.bitrate // 1000} kbps", None))

                rows.append(("---", "", None))   # separator

                if audio.tags:
                    for key, val in sorted(audio.tags.items()):
                        label = _TAG_LABELS.get(key, key)
                        text  = val[0] if isinstance(val, list) and val else str(val)
                        rows.append((label, str(text), key))   # editable
                else:
                    rows.append(("(태그 없음)", "", None))
        except Exception as e:
            self._status_label.setText(f"오류: {e}")

        self._table.setRowCount(len(rows))
        for r, (key, val, tag_key) in enumerate(rows):
            key_item = QTableWidgetItem(key)
            val_item = QTableWidgetItem(val)

            if tag_key is not None:
                # Editable tag row: store the easy-tag key for saving later
                self._tag_keys[r] = tag_key
                key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            else:
                # Read-only summary / stream info row — use an explicit mid-gray
                # so the text stays readable regardless of light or dark theme.
                key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                val_item.setFlags(val_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                dim = QBrush(QColor(130, 130, 130))
                key_item.setForeground(dim)
                val_item.setForeground(dim)

            self._table.setItem(r, 0, key_item)
            self._table.setItem(r, 1, val_item)


def _fmt_duration(seconds) -> str:
    """Convert seconds to 'm:ss' string (e.g. 100 -> '1:40')."""
    if not seconds:
        return "-"
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"
