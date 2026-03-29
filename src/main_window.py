"""
main_window.py - PyQt6 UI for the MP3 archive manager.

Provides a main window with:
  - Directory path configurator (persisted via QSettings)
  - Browse button to open a system file explorer and select a directory
  - Scan button to recursively find all MP3 files under the configured path
  - Progress bar updated during scan via QThread
  - Table view listing all stored MP3 records
  - Delete button to remove selected records from the database

The window layout is defined in main_window.ui and can be edited
with Qt Designer without touching this file.

Usage:
    python src/main_window.py [--db <db_path>]
"""

import argparse
import base64
import os
import sys

from mutagen import File as MutagenFile
from PyQt6 import uic
from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHeaderView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QTableWidgetItem,
)

from mp3_manager import Mp3Manager


def _fmt_duration(seconds) -> str:
    """Convert a duration in seconds to 'm:ss' format (e.g. 100 -> '1:40')."""
    if not seconds:
        return "-"
    total = int(seconds)
    return f"{total // 60}:{total % 60:02d}"


def _get_album_art(file_path: str) -> bytes | None:
    """
    Extract embedded album art from an audio file.

    Supports ID3 (APIC), FLAC/Ogg (pictures), and MP4/M4A (covr).
    Returns the raw image bytes, or None if no art is found.

    Args:
        file_path: Path to the audio file.
    """
    try:
        audio = MutagenFile(file_path)
        if audio is None:
            return None
        # ID3 tags (MP3, AIFF): look for any APIC frame
        if audio.tags:
            for key in audio.tags.keys():
                if key.startswith("APIC"):
                    return audio.tags[key].data
        # FLAC / Ogg Vorbis / Opus: pictures attribute
        if hasattr(audio, "pictures") and audio.pictures:
            return audio.pictures[0].data
        # MP4 / M4A / AAC: covr atom
        if audio.tags and "covr" in audio.tags:
            return bytes(audio.tags["covr"][0])
    except Exception:
        pass
    return None


def _album_art_tooltip(file_path: str) -> str:
    """
    Build a tooltip string for a filename cell.

    Returns an HTML <img> tag with the embedded album art encoded as
    base64 when art is available, otherwise returns the plain file path.

    Args:
        file_path: Absolute path to the audio file.
    """
    art = _get_album_art(file_path)
    if art:
        b64 = base64.b64encode(art).decode("ascii")
        return (
            f'<img src="data:image/jpeg;base64,{b64}" '
            f'width="160" height="160"><br><small>{file_path}</small>'
        )
    return file_path
from tag_fetch_dialog import TagFetchDialog
from song_info_dialog import SongInfoDialog
from tag_detail_dialog import TagDetailDialog

# Path to the Qt Designer UI file.
# When frozen by PyInstaller (sys._MEIPASS), the .ui file is extracted
# to the temp bundle directory; otherwise it lives next to this module.
_BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
_UI_FILE = os.path.join(_BASE_DIR, "main_window.ui")

# QSettings keys
_SETTINGS_ORG  = "mp3-archive"
_SETTINGS_APP  = "MP3ArchiveManager"
_KEY_LAST_PATH = "scan/last_path"


class ScanWorker(QThread):
    """
    Background worker that runs Mp3Manager.scan() on a separate thread.

    Emits progress signals so the UI can update without freezing.
    """

    progress = pyqtSignal(int, int, str)        # current, total, file_path
    finished = pyqtSignal(int, int)             # processed, skipped

    def __init__(self, manager: Mp3Manager, directory: str, force: bool = False) -> None:
        """
        Initialize the worker.

        Args:
            manager:   Shared Mp3Manager instance.
            directory: Directory path to scan recursively.
            force:     When True, re-read every file (full rescan).
        """
        super().__init__()
        self._manager = manager
        self._directory = directory
        self._force = force

    def run(self) -> None:
        """Execute the scan and emit progress/finished signals."""
        processed, skipped = self._manager.scan(
            self._directory,
            progress_callback=lambda cur, tot, path: self.progress.emit(cur, tot, path),
            force=self._force,
        )
        self.finished.emit(processed, skipped)


class MainWindow(QMainWindow):
    """
    Main application window for the MP3 archive manager.

    Layout is loaded from main_window.ui; this class wires up
    signals/slots, drives the Mp3Manager backend, and persists
    the last-used directory path across sessions via QSettings.
    """

    def __init__(self, db_path: str) -> None:
        """
        Load the UI file, restore saved path, connect signals, and open the database.

        Args:
            db_path: Path to the SQLite database file.
        """
        super().__init__()
        uic.loadUi(_UI_FILE, self)

        self._manager  = Mp3Manager(db_path)
        self._worker: ScanWorker | None = None
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)

        self._connect_signals()
        self._setup_table()
        self._restore_path()
        self._load_table()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Connect all button click signals to their handler slots."""
        self.btn_browse.clicked.connect(self._on_browse_clicked)
        self.btn_scan.clicked.connect(self._on_scan_clicked)
        self.btn_force_scan.clicked.connect(self._on_force_scan_clicked)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_tag_fetch.clicked.connect(self._on_tag_fetch_clicked)
        self.btn_search.clicked.connect(self._on_search_clicked)
        self.btn_search_clear.clicked.connect(self._on_search_clear_clicked)
        self.search_edit.returnPressed.connect(self._on_search_clicked)
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        self.chk_search_tags.toggled.connect(self._on_search_text_changed)

    def _setup_table(self) -> None:
        """Apply column resize modes, enable sorting, and set up context menus."""
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._on_column_visibility_menu)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        self._restore_column_visibility()

    def _restore_path(self) -> None:
        """Load the last-used directory path from QSettings and display it."""
        saved = self._settings.value(_KEY_LAST_PATH, "")
        if saved:
            self.path_edit.setText(saved)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_browse_clicked(self) -> None:
        """
        Open the system file explorer to select a directory.

        The chosen path is saved to QSettings and shown in path_edit.
        """
        start_dir = self.path_edit.text() or os.path.expanduser("~")
        directory = QFileDialog.getExistingDirectory(
            self, "MP3 경로 선택", start_dir
        )
        if not directory:
            return
        self.path_edit.setText(directory)
        self._settings.setValue(_KEY_LAST_PATH, directory)

    def _on_scan_clicked(self) -> None:
        """Start an incremental scan: only new or modified files are processed."""
        self._start_scan(force=False)

    def _on_force_scan_clicked(self) -> None:
        """Start a full rescan: every file is re-read regardless of cached timestamps."""
        self._start_scan(force=True)

    def _start_scan(self, force: bool) -> None:
        """
        Validate the configured path and launch ScanWorker.

        Args:
            force: Passed to ScanWorker to control incremental vs full scan.
        """
        directory = self.path_edit.text().strip()
        if not directory:
            QMessageBox.warning(self, "경고", "먼저 음악 경로를 설정해주세요.")
            return
        if not os.path.isdir(directory):
            QMessageBox.warning(self, "경고", f"'{directory}' 는 유효한 디렉토리가 아닙니다.")
            return

        self.btn_browse.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.btn_force_scan.setEnabled(False)
        self.btn_delete.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        label = "전체 스캔 중" if force else "빠른 스캔 중"
        self.status_label.setText(f"{label}: {directory}")

        self._worker = ScanWorker(self._manager, directory, force=force)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished.connect(self._on_scan_finished)
        self._worker.start()

    def _on_scan_progress(self, current: int, total: int, path: str) -> None:
        """
        Update the progress bar as each file is scanned.

        Args:
            current: 1-based index of the file just processed.
            total:   Total number of MP3 files found in the directory.
            path:    Absolute path of the file just processed.
        """
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(os.path.basename(path))

    def _on_scan_finished(self, processed: int, skipped: int) -> None:
        """
        Refresh the table and re-enable controls after scan completes.

        Args:
            processed: Number of files that were read and saved.
            skipped:   Number of unchanged files that were skipped.
        """
        self.progress_bar.setVisible(False)
        self.btn_browse.setEnabled(True)
        self.btn_scan.setEnabled(True)
        self.btn_force_scan.setEnabled(True)
        self.btn_delete.setEnabled(True)
        self.status_label.setText(
            f"완료: {processed}개 업데이트, {skipped}개 변경 없음"
        )
        self._load_table()

    def _on_table_context_menu(self, pos) -> None:
        """
        Show a right-click context menu on the table.

        Provides '인터넷에서 정보 보기' and '태그 찾기' actions
        for the row under the cursor.

        Args:
            pos: Cursor position relative to the table viewport.
        """
        index = self.table.indexAt(pos)
        if not index.isValid():
            return

        row = index.row()
        path = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        files = self._manager.list_files()
        file_info = next((f for f in files if f["path"] == path), None)
        if file_info is None:
            return

        menu = QMenu(self)
        action_detail = menu.addAction("자세히")
        menu.addSeparator()
        action_info   = menu.addAction("인터넷에서 정보 보기")
        action_tag    = menu.addAction("태그 찾기")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))

        if action == action_detail:
            dlg = TagDetailDialog(file_info, parent=self)
            dlg.exec()
        elif action == action_info:
            dlg = SongInfoDialog(self._manager, file_info, parent=self)
            dlg.exec()
            self._load_table()
        elif action == action_tag:
            dlg = TagFetchDialog(self._manager, [file_info], parent=self)
            dlg.exec()
            self._load_table()

    def _on_tag_fetch_clicked(self) -> None:
        """
        Open the TagFetchDialog for all selected rows.

        If no rows are selected, process all files in the table that
        are missing a title or artist tag.
        """
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            paths = {
                self.table.item(idx.row(), 0).data(Qt.ItemDataRole.UserRole)
                for idx in selected_rows
            }
            files = [f for f in self._manager.list_files() if f["path"] in paths]
        else:
            files = self._manager.list_files()

        dlg = TagFetchDialog(self._manager, files, parent=self)
        dlg.exec()
        self._load_table()

    def _on_search_text_changed(self, text=None) -> None:
        """
        Filter the table in real time as the user types or toggles the checkbox.

        Args:
            text: Current text in search_edit (ignored; read directly from widget).
        """
        keyword = self.search_edit.text().strip()
        if keyword:
            filename_only = not self.chk_search_tags.isChecked()
            files = self._manager.search(keyword, filename_only=filename_only)
            self.status_label.setText(f"검색 결과: {len(files)}개")
        else:
            files = self._manager.list_files()
            self.status_label.setText("준비")
        self._fill_table(files)

    def _on_search_clicked(self) -> None:
        """
        Filter the table by the keyword entered in search_edit.

        Shows all records when the keyword is empty (equivalent to clear).
        """
        keyword = self.search_edit.text().strip()
        if keyword:
            filename_only = not self.chk_search_tags.isChecked()
            files = self._manager.search(keyword, filename_only=filename_only)
            self.status_label.setText(f"검색 결과: {len(files)}개")
        else:
            files = self._manager.list_files()
            self.status_label.setText("준비")
        self._fill_table(files)

    def _on_search_clear_clicked(self) -> None:
        """Clear the search field and restore the full table."""
        self.search_edit.clear()
        self._load_table()
        self.status_label.setText("준비")

    def _on_delete_clicked(self) -> None:
        """Delete all selected rows from the database and refresh the table."""
        selected_rows = self.table.selectionModel().selectedRows()
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
            path = self.table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
            self._manager.delete(path)

        self._load_table()
        self.status_label.setText(f"{len(selected_rows)}개 항목 삭제됨")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_table(self) -> None:
        """Fetch all records from the database and populate the table."""
        self._fill_table(self._manager.list_files())

    def _fill_table(self, files: list) -> None:
        """
        Populate the table widget with the given list of MP3 records.

        Sorting is temporarily disabled during insertion to prevent
        rows from being reordered mid-fill.

        Args:
            files: List of row dicts as returned by Mp3Manager.list_files()
                   or Mp3Manager.search().
        """
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(files))
        for row, f in enumerate(files):
            filename_item = QTableWidgetItem(f["filename"])
            filename_item.setData(Qt.ItemDataRole.UserRole, f["path"])
            filename_item.setToolTip(_album_art_tooltip(f["path"]))

            path_item = QTableWidgetItem(f["path"])
            path_item.setToolTip(f["path"])

            duration = _fmt_duration(f["duration"])
            filesize = str(f["filesize"]) if f["filesize"] else "-"

            def _item(text: str) -> QTableWidgetItem:
                """Create a table item whose tooltip matches its text."""
                it = QTableWidgetItem(text)
                it.setToolTip(text)
                return it

            self.table.setItem(row, 0, filename_item)
            self.table.setItem(row, 1, path_item)
            self.table.setItem(row, 2, _item(f["title"] or "-"))
            self.table.setItem(row, 3, _item(f["artist"] or "-"))
            self.table.setItem(row, 4, _item(f["album"] or "-"))
            self.table.setItem(row, 5, _item(f.get("genre") or "-"))
            self.table.setItem(row, 6, _item(f.get("year") or "-"))
            self.table.setItem(row, 7, _item(duration))
            self.table.setItem(row, 8, _item(filesize))
            self.table.setItem(row, 9, _item(f["file_created_at"] or "-"))
            self.table.setItem(row, 10, _item(f["file_modified_at"] or "-"))

        self.table.setSortingEnabled(True)

    def _on_column_visibility_menu(self, pos) -> None:
        """
        Show a right-click menu on the table header to toggle column visibility.

        Each column is listed as a checkable action.  Clicking an action
        toggles that column's hidden state and persists the choice to QSettings.

        Args:
            pos: Cursor position relative to the header viewport.
        """
        menu = QMenu(self)
        hdr = self.table.horizontalHeader()
        for col in range(self.table.columnCount()):
            label = self.table.horizontalHeaderItem(col).text()
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(not self.table.isColumnHidden(col))
            action.setData(col)

        chosen = menu.exec(hdr.mapToGlobal(pos))
        if chosen is None:
            return

        col = chosen.data()
        self.table.setColumnHidden(col, not self.table.isColumnHidden(col))
        self._save_column_visibility()

    def _save_column_visibility(self) -> None:
        """Persist the set of hidden column indices to QSettings."""
        hidden = [
            col for col in range(self.table.columnCount())
            if self.table.isColumnHidden(col)
        ]
        self._settings.setValue("table/hidden_columns", hidden)

    def _restore_column_visibility(self) -> None:
        """Restore hidden column indices from QSettings."""
        hidden = self._settings.value("table/hidden_columns", [])
        # QSettings may return a single string when only one value was saved
        if isinstance(hidden, str):
            hidden = [hidden]
        for col in hidden:
            self.table.setColumnHidden(int(col), True)

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
