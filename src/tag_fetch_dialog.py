"""
tag_fetch_dialog.py - Dialog for reviewing and applying tag suggestions.

Steps through a list of audio files that are missing title or artist tags,
fetches candidates from MusicBrainz and/or iTunes in a background thread,
and lets the user apply or skip each suggestion.

Usage (from MainWindow):
    files = self._manager.list_files()  # or selected rows
    dlg = TagFetchDialog(self._manager, files, parent=self)
    dlg.exec()
    self._load_table()  # refresh after dialog closes
"""

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

import tag_fetcher
import itunes_fetcher

# Source identifiers used internally
_SRC_MB     = "musicbrainz"
_SRC_ITUNES = "itunes"
_SRC_BOTH   = "both"

# Human-readable labels for the source combo box
_SOURCE_LABELS = [
    ("MusicBrainz",         _SRC_MB),
    ("iTunes",              _SRC_ITUNES),
    ("둘 다 (Both)",         _SRC_BOTH),
]


class _FetchWorker(QThread):
    """
    Background thread that queries one or both tag sources for a single file.

    Emits finished(candidates) when the search completes.
    Each candidate dict includes a 'source' key ("MusicBrainz" or "iTunes").
    """

    finished = pyqtSignal(list)

    def __init__(
        self,
        artist: str | None,
        title: str | None,
        source: str = _SRC_MB,
    ) -> None:
        """
        Args:
            artist: Artist name to search (may be None).
            title:  Recording title to search (may be None).
            source: One of _SRC_MB, _SRC_ITUNES, or _SRC_BOTH.
        """
        super().__init__()
        self._artist = artist
        self._title  = title
        self._source = source

    def run(self) -> None:
        """Execute the search(es) and emit combined results."""
        results: list[dict] = []

        if self._source in (_SRC_MB, _SRC_BOTH):
            for c in tag_fetcher.search(self._artist, self._title):
                c["source"] = "MusicBrainz"
                results.append(c)

        if self._source in (_SRC_ITUNES, _SRC_BOTH):
            for c in itunes_fetcher.search(self._artist, self._title):
                c["source"] = "iTunes"
                results.append(c)

        # Sort combined results by score descending.
        results.sort(key=lambda c: c.get("score", 0), reverse=True)
        self.finished.emit(results)


class TagFetchDialog(QDialog):
    """
    Step-through dialog for completing missing audio tags.

    Supports searching MusicBrainz, iTunes, or both sources simultaneously.
    Only files whose title or artist field is absent (None or '-') are
    included in the processing queue.  For each file the dialog:
      1. Searches the selected source(s) in the background.
      2. Shows up to 7 candidates in a table.
      3. Lets the user select one row and click 적용, or click 건너뛰기.
      4. On 적용, writes the chosen tags to both the file and the DB.
    """

    def __init__(self, manager, files: list[dict], parent=None) -> None:
        """
        Args:
            manager: Mp3Manager instance used to write tag updates.
            files:   List of row dicts as returned by Mp3Manager.list_files()
                     or Mp3Manager.search().  Only files missing title or
                     artist are queued.
            parent:  Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("태그 자동 완성")
        self.resize(780, 480)

        self._manager = manager
        self._files = [
            f for f in files
            if not f.get("title") or f.get("title") == "-"
            or not f.get("artist") or f.get("artist") == "-"
        ]
        self._index = 0
        self._worker: _FetchWorker | None = None
        self._applied_count = 0

        self._build_ui()

        if self._files:
            self._load_current()
        else:
            self._status_label.setText("태그가 없는 파일이 없습니다.")
            self._btn_apply.setEnabled(False)
            self._btn_skip.setEnabled(False)
            self._progress.setVisible(False)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create and arrange all child widgets."""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self._counter_label = QLabel("")
        self._file_label    = QLabel("파일: -")
        self._query_label   = QLabel("검색어: -")
        layout.addWidget(self._counter_label)
        layout.addWidget(self._file_label)
        layout.addWidget(self._query_label)

        # Source selector
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("검색 소스:"))
        self._source_combo = QComboBox()
        for label, _ in _SOURCE_LABELS:
            self._source_combo.addItem(label)
        # Default to iTunes for better Korean coverage
        self._source_combo.setCurrentIndex(1)
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)
        src_row.addWidget(self._source_combo)
        src_row.addStretch()
        layout.addLayout(src_row)

        # Results table — 6 columns: 점수, 제목, 아티스트, 앨범, 연도, 출처
        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["점수", "제목", "아티스트", "앨범", "연도", "출처"]
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self._table)

        # Status / indeterminate progress bar
        self._status_label = QLabel("")
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # indeterminate spinner
        self._progress.setFixedHeight(6)
        layout.addWidget(self._status_label)
        layout.addWidget(self._progress)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_apply = QPushButton("적용")
        self._btn_skip  = QPushButton("건너뛰기")
        self._btn_close = QPushButton("닫기")
        self._btn_apply.setEnabled(False)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_apply)
        btn_row.addWidget(self._btn_skip)
        btn_row.addWidget(self._btn_close)
        layout.addLayout(btn_row)

        self._btn_apply.clicked.connect(self._on_apply)
        self._btn_skip.clicked.connect(self._on_skip)
        self._btn_close.clicked.connect(self.accept)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _current_source(self) -> str:
        """Return the internal source identifier for the current combo selection."""
        idx = self._source_combo.currentIndex()
        return _SOURCE_LABELS[idx][1]

    def _load_current(self) -> None:
        """Populate labels and start a background search for the current file."""
        if self._index >= len(self._files):
            self._on_all_done()
            return

        f = self._files[self._index]
        artist = f.get("artist") if f.get("artist") not in (None, "-") else None
        title  = f.get("title")  if f.get("title")  not in (None, "-") else None

        total = len(self._files)
        self._counter_label.setText(f"({self._index + 1} / {total})")
        self._file_label.setText(f"파일: {f['filename']}")
        self._query_label.setText(f"검색어: {artist or '?'} / {title or '?'}")

        self._table.setRowCount(0)
        self._status_label.setText("검색 중...")
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._btn_apply.setEnabled(False)
        self._btn_skip.setEnabled(True)

        # Stop any previous worker before starting a new one.
        if self._worker and self._worker.isRunning():
            self._worker.finished.disconnect()
            self._worker.quit()
            self._worker.wait()

        self._worker = _FetchWorker(artist, title, self._current_source())
        self._worker.finished.connect(self._on_fetch_done)
        self._worker.start()

    def _on_all_done(self) -> None:
        """Called when every file has been processed."""
        self._status_label.setText(
            f"완료: {self._applied_count}개 적용됨 / {len(self._files)}개 처리됨"
        )
        self._progress.setVisible(False)
        self._btn_apply.setEnabled(False)
        self._btn_skip.setEnabled(False)
        self._counter_label.setText("")
        self._file_label.setText("")
        self._query_label.setText("")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_source_changed(self, _index: int) -> None:
        """Re-run the search when the user changes the source selection."""
        if self._files and self._index < len(self._files):
            self._load_current()

    def _on_fetch_done(self, candidates: list) -> None:
        """
        Populate the candidate table with search results.

        Args:
            candidates: List of dicts from tag_fetcher or itunes_fetcher,
                        each containing a 'source' key.
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
            self._table.setItem(row, 5, QTableWidgetItem(c.get("source", "")))

        self._table.selectRow(0)
        self._btn_apply.setEnabled(True)

    def _on_apply(self) -> None:
        """Write the selected candidate's tags to the file and DB, then advance."""
        row = self._table.currentRow()
        if row < 0:
            return

        title  = self._table.item(row, 1).text() or None
        artist = self._table.item(row, 2).text() or None
        album  = self._table.item(row, 3).text() or None

        path = self._files[self._index]["path"]
        self._manager.update_file_tags(path, title, artist, album)
        self._applied_count += 1

        self._index += 1
        self._load_current()

    def _on_skip(self) -> None:
        """Skip the current file without making any changes."""
        self._index += 1
        self._load_current()
