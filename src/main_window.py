"""
main_window.py - PyQt6 UI for the MP3 archive manager.

Provides a main window with:
  - Directory picker to scan for MP3 files
  - Progress bar updated during scan via QThread
  - Table view listing all stored MP3 records
  - Delete button to remove selected records from the database

Usage:
    python src/main_window.py [--db <db_path>]
"""

import argparse
import os
import sys

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mp3_manager import Mp3Manager


class ScanWorker(QThread):
    """
    Background worker that runs Mp3Manager.scan() on a separate thread.

    Emits progress signals so the UI can update without freezing.
    """

    progress = pyqtSignal(int, int, str)   # current, total, file_path
    finished = pyqtSignal(int)             # total files scanned

    def __init__(self, manager: Mp3Manager, directory: str) -> None:
        """
        Initialize the worker.

        Args:
            manager:   Shared Mp3Manager instance.
            directory: Directory path to scan.
        """
        super().__init__()
        self._manager = manager
        self._directory = directory

    def run(self) -> None:
        """Execute the scan and emit progress/finished signals."""
        count = self._manager.scan(
            self._directory,
            progress_callback=lambda cur, tot, path: self.progress.emit(cur, tot, path),
        )
        self.finished.emit(count)


class MainWindow(QMainWindow):
    """
    Main application window for the MP3 archive manager.

    Displays a toolbar for scanning and a table of stored MP3 records.
    """

    def __init__(self, db_path: str) -> None:
        """
        Set up the window, widgets, and the Mp3Manager instance.

        Args:
            db_path: Path to the SQLite database file.
        """
        super().__init__()
        self._manager = Mp3Manager(db_path)
        self._worker: ScanWorker | None = None

        self.setWindowTitle("MP3 Archive Manager")
        self.resize(900, 580)

        self._build_ui()
        self._load_table()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create and arrange all widgets in the main window."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 12, 12, 12)

        # --- toolbar row ---
        toolbar = QHBoxLayout()

        self._btn_scan = QPushButton("디렉토리 스캔")
        self._btn_scan.setFixedWidth(140)
        self._btn_scan.clicked.connect(self._on_scan_clicked)

        self._btn_delete = QPushButton("선택 삭제")
        self._btn_delete.setFixedWidth(100)
        self._btn_delete.clicked.connect(self._on_delete_clicked)

        self._status_label = QLabel("준비")

        toolbar.addWidget(self._btn_scan)
        toolbar.addWidget(self._btn_delete)
        toolbar.addStretch()
        toolbar.addWidget(self._status_label)
        layout.addLayout(toolbar)

        # --- progress bar ---
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # --- table ---
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(
            ["파일명", "제목", "아티스트", "앨범", "길이(초)", "크기(bytes)", "생성일시", "수정일시"]
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_scan_clicked(self) -> None:
        """Open a directory picker and start the background scan worker."""
        directory = QFileDialog.getExistingDirectory(self, "스캔할 디렉토리 선택")
        if not directory:
            return

        self._btn_scan.setEnabled(False)
        self._btn_delete.setEnabled(False)
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._status_label.setText(f"스캔 중: {directory}")

        self._worker = ScanWorker(self._manager, directory)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.start()

    def _on_scan_progress(self, current: int, total: int, path: str) -> None:
        """
        Update the progress bar during a scan.

        Args:
            current: 1-based index of the file just processed.
            total:   Total number of MP3 files in the directory.
            path:    Path of the file just processed.
        """
        self._progress.setMaximum(total)
        self._progress.setValue(current)
        self._status_label.setText(os.path.basename(path))

    def _on_scan_finished(self, count: int) -> None:
        """
        Refresh the table and re-enable controls after scan completes.

        Args:
            count: Number of MP3 files that were scanned and saved.
        """
        self._progress.setVisible(False)
        self._btn_scan.setEnabled(True)
        self._btn_delete.setEnabled(True)
        self._status_label.setText(f"완료: {count}개 파일 저장됨")
        self._load_table()

    def _on_delete_clicked(self) -> None:
        """Delete all selected rows from the database and refresh the table."""
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "알림", "삭제할 항목을 선택해주세요.")
            return

        confirm = QMessageBox.question(
            self,
            "삭제 확인",
            f"선택한 {len(selected_rows)}개 항목을 삭제할까요?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        for index in selected_rows:
            path = self._table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
            self._manager.delete(path)

        self._load_table()
        self._status_label.setText(f"{len(selected_rows)}개 항목 삭제됨")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_table(self) -> None:
        """Fetch all records from the database and populate the table."""
        files = self._manager.list_files()
        self._table.setRowCount(len(files))
        for row, f in enumerate(files):
            filename_item = QTableWidgetItem(f["filename"])
            filename_item.setData(Qt.ItemDataRole.UserRole, f["path"])

            duration = f"{f['duration']:.1f}" if f["duration"] else "-"
            filesize = str(f["filesize"]) if f["filesize"] else "-"

            self._table.setItem(row, 0, filename_item)
            self._table.setItem(row, 1, QTableWidgetItem(f["title"] or "-"))
            self._table.setItem(row, 2, QTableWidgetItem(f["artist"] or "-"))
            self._table.setItem(row, 3, QTableWidgetItem(f["album"] or "-"))
            self._table.setItem(row, 4, QTableWidgetItem(duration))
            self._table.setItem(row, 5, QTableWidgetItem(filesize))
            self._table.setItem(row, 6, QTableWidgetItem(f["file_created_at"] or "-"))
            self._table.setItem(row, 7, QTableWidgetItem(f["file_modified_at"] or "-"))

    def closeEvent(self, event) -> None:
        """Close the database connection when the window is closed."""
        self._manager.close()
        super().closeEvent(event)


def main() -> None:
    """Parse CLI arguments, create the application, and start the event loop."""
    parser = argparse.ArgumentParser(description="MP3 Archive Manager UI")
    parser.add_argument("--db", default="mp3_archive.db", help="SQLite database file path")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MainWindow(args.db)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
