"""
song_info_dialog.py - Popup dialog showing MusicBrainz information for a single song.

Fetches candidates in a background thread and displays them in a table.
Optionally lets the user apply a selected result as new tags.

Usage (from a context menu handler):
    row = ...  # dict from Mp3Manager.list_files()
    dlg = SongInfoDialog(manager, row, parent=self)
    dlg.exec()
    self._load_table()  # refresh if tags were applied
"""

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QFrame,
)

import tag_fetcher


class _FetchWorker(QThread):
    """Background thread that queries MusicBrainz for a single file."""

    finished = pyqtSignal(list)

    def __init__(self, artist: str | None, title: str | None) -> None:
        """
        Args:
            artist: Artist name to search (may be None).
            title:  Recording title to search (may be None).
        """
        super().__init__()
        self._artist = artist
        self._title = title

    def run(self) -> None:
        """Execute the MusicBrainz search and emit results."""
        self.finished.emit(tag_fetcher.search(self._artist, self._title))


class SongInfoDialog(QDialog):
    """
    Read/write popup that shows MusicBrainz search results for one song.

    Displays the file's current metadata at the top, then fetches and
    shows up to 7 candidates from MusicBrainz.  The user can select
    a row and click '태그 적용' to write the chosen tags to the file
    and database, or simply close the dialog.
    """

    def __init__(self, manager, file_info: dict, parent=None) -> None:
        """
        Args:
            manager:   Mp3Manager instance used to write tag updates.
            file_info: Row dict as returned by Mp3Manager.list_files().
            parent:    Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("인터넷 정보 검색")
        self.resize(740, 480)

        self._manager   = manager
        self._file_info = file_info
        self._worker: _FetchWorker | None = None

        self._build_ui()
        self._start_fetch()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create and arrange all child widgets."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Current file info section
        info = self._file_info
        layout.addWidget(QLabel(f"<b>파일:</b> {info.get('filename', '-')}"))

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        cur_layout = QHBoxLayout()
        cur_layout.addWidget(QLabel(f"<b>현재 제목:</b> {info.get('title') or '-'}"))
        cur_layout.addWidget(QLabel(f"<b>아티스트:</b> {info.get('artist') or '-'}"))
        cur_layout.addWidget(QLabel(f"<b>앨범:</b> {info.get('album') or '-'}"))
        cur_layout.addStretch()
        layout.addLayout(cur_layout)

        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line2)

        layout.addWidget(QLabel("인터넷 검색 결과:"))

        # Results table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["점수", "제목", "아티스트", "앨범", "연도"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table)

        # Status / indeterminate progress bar
        self._status_label = QLabel("검색 중...")
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setFixedHeight(6)
        layout.addWidget(self._status_label)
        layout.addWidget(self._progress)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_apply = QPushButton("태그 적용")
        self._btn_close = QPushButton("닫기")
        self._btn_apply.setEnabled(False)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_apply)
        btn_row.addWidget(self._btn_close)
        layout.addLayout(btn_row)

        self._btn_apply.clicked.connect(self._on_apply)
        self._btn_close.clicked.connect(self.accept)

    # ------------------------------------------------------------------
    # Background fetch
    # ------------------------------------------------------------------

    def _start_fetch(self) -> None:
        """Start a background MusicBrainz search for this file."""
        info   = self._file_info
        artist = info.get("artist") if info.get("artist") not in (None, "-") else None
        title  = info.get("title")  if info.get("title")  not in (None, "-") else None

        self._worker = _FetchWorker(artist, title)
        self._worker.finished.connect(self._on_fetch_done)
        self._worker.start()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_fetch_done(self, candidates: list) -> None:
        """
        Populate the results table with MusicBrainz candidates.

        Args:
            candidates: List of dicts from tag_fetcher.search().
        """
        self._progress.setVisible(False)
        self._progress.setRange(0, 1)

        if not candidates:
            self._status_label.setText("검색 결과 없음")
            return

        self._status_label.setText(f"{len(candidates)}개 후보 검색됨")
        self._table.setRowCount(len(candidates))
        for row, c in enumerate(candidates):
            self._table.setItem(row, 0, QTableWidgetItem(str(c.get("score", ""))))
            self._table.setItem(row, 1, QTableWidgetItem(c.get("title",  "")))
            self._table.setItem(row, 2, QTableWidgetItem(c.get("artist", "")))
            self._table.setItem(row, 3, QTableWidgetItem(c.get("album",  "")))
            self._table.setItem(row, 4, QTableWidgetItem(c.get("year",   "")))

        self._table.selectRow(0)
        self._btn_apply.setEnabled(True)

    def _on_apply(self) -> None:
        """Write the selected candidate's tags to the file and DB, then close."""
        row = self._table.currentRow()
        if row < 0:
            return

        title  = self._table.item(row, 1).text() or None
        artist = self._table.item(row, 2).text() or None
        album  = self._table.item(row, 3).text() or None

        self._manager.update_file_tags(
            self._file_info["path"], title, artist, album
        )
        self.accept()
