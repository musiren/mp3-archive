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

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QFrame,
)

from mutagen import File as MutagenFile


class TagDetailDialog(QDialog):
    """
    Read-only dialog that shows every tag embedded in an audio file.

    Tag keys and values are read via mutagen and displayed in a two-column
    table (태그 / 값).  The dialog also shows a summary row (filename,
    format, duration, filesize) at the top.
    """

    def __init__(self, file_info: dict, parent=None) -> None:
        """
        Args:
            file_info: Row dict as returned by Mp3Manager.list_files().
            parent:    Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("자세히 — 태그 정보")
        self.resize(640, 500)

        self._file_info = file_info
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

        # Summary header
        layout.addWidget(QLabel(f"<b>파일:</b> {info.get('filename', '-')}"))
        layout.addWidget(QLabel(f"<b>경로:</b> {path}"))

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # Tag table
        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["태그", "값"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(True)
        layout.addWidget(self._table)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        btn_close = QPushButton("닫기")
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        btn_close.clicked.connect(self.accept)

        self._load_tags(path)

    def showEvent(self, event) -> None:
        """Set initial column widths to 30 / 70 % of the table width."""
        super().showEvent(event)
        total = self._table.viewport().width()
        self._table.setColumnWidth(0, int(total * 0.30))
        self._table.setColumnWidth(1, int(total * 0.70))

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
        rows: list[tuple[str, str]] = []

        # --- File-level summary from DB ---
        info = self._file_info
        rows.append(("크기", f"{info.get('filesize', '-')} bytes"))
        rows.append(("길이", _fmt_duration(info.get("duration"))))
        rows.append(("생성일시", info.get("file_created_at") or "-"))
        rows.append(("수정일시", info.get("file_modified_at") or "-"))

        # --- Tags from file ---
        try:
            audio = MutagenFile(path)
            if audio is None:
                self._status_label.setText("파일을 읽을 수 없습니다.")
            else:
                # Audio stream info
                if hasattr(audio, "info"):
                    ai = audio.info
                    if hasattr(ai, "sample_rate"):
                        rows.append(("샘플레이트", f"{ai.sample_rate} Hz"))
                    if hasattr(ai, "channels"):
                        rows.append(("채널", str(ai.channels)))
                    if hasattr(ai, "bitrate"):
                        rows.append(("비트레이트", f"{ai.bitrate // 1000} kbps"))

                rows.append(("---", ""))   # separator

                if audio.tags:
                    for key, val in sorted(audio.tags.items()):
                        rows.append((str(key), str(val)))
                else:
                    rows.append(("(태그 없음)", ""))
        except Exception as e:
            self._status_label.setText(f"오류: {e}")

        self._table.setRowCount(len(rows))
        for r, (key, val) in enumerate(rows):
            self._table.setItem(r, 0, QTableWidgetItem(key))
            self._table.setItem(r, 1, QTableWidgetItem(val))


def _fmt_duration(seconds) -> str:
    """Convert seconds to 'm:ss' string (e.g. 100 -> '1:40')."""
    if not seconds:
        return "-"
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"
