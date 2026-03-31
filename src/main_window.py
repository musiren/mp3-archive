from __future__ import annotations

"""
main_window.py - PyQt6 UI for the MP3 archive manager.

Provides a main window with:
  - Directory path configurator (persisted via QSettings)
  - Browse button to open a system file explorer and select a directory
  - Scan button to recursively find all MP3 files under the configured path
  - Progress bar updated during scan via QThread
  - Table view listing all stored MP3 records
  - Delete button to remove selected records from the database
  - Playlist panel: drag-and-drop from table, double-click to play
  - Playback controls: play/pause, stop, previous, next, seek slider

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
from PyQt6.QtCore import Qt, QSettings, QThread, QUrl, pyqtSignal

try:
    from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
    _MULTIMEDIA_AVAILABLE = True
except ImportError:
    _MULTIMEDIA_AVAILABLE = False

from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHeaderView,
    QListWidgetItem,
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


def _fmt_ms(ms: int) -> str:
    """Convert a duration in milliseconds to 'm:ss' format."""
    if ms <= 0:
        return "0:00"
    total = ms // 1000
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

    Includes a playlist panel (right side) where users can drag files
    from the MP3 table and double-click to play them via QMediaPlayer.
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

        # Make only the splitter (table + playlist) grow when the window is resized.
        # Items: 0=pathLayout 1=searchLayout 2=toolbarLayout 3=progress_bar 4=splitter
        self.centralWidget().layout().setStretch(4, 1)

        self._setup_player()
        self._connect_signals()
        self._setup_table()
        self._setup_playlist()
        self._restore_path()
        self._load_table()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _setup_player(self) -> None:
        """Initialise QMediaPlayer and QAudioOutput for audio playback.

        When the QtMultimedia library is not available (e.g. in headless
        test environments without audio hardware), the player is set to
        None and playback features are silently disabled.
        """
        self._seeking = False  # guard to prevent slider feedback loop
        # Playback mode cycles: sequential → repeat_one → repeat_all → shuffle
        self._play_mode = "sequential"
        if not _MULTIMEDIA_AVAILABLE:
            self._player = None
            self._audio_output = None
            return

        self._audio_output = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(1.0)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)

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

        # Playback controls
        self.btn_play_pause.clicked.connect(self._on_play_pause_clicked)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        self.btn_prev.clicked.connect(self._on_prev_clicked)
        self.btn_next.clicked.connect(self._on_next_clicked)
        self.btn_playlist_clear.clicked.connect(self._on_playlist_clear_clicked)
        self.btn_playlist_save.clicked.connect(self._on_playlist_save_clicked)
        self.btn_playlist_load.clicked.connect(self._on_playlist_load_clicked)
        self.btn_play_mode.clicked.connect(self._on_play_mode_clicked)

        # Seek slider
        self.seek_slider.sliderPressed.connect(self._on_seek_slider_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_slider_released)

        # Volume slider
        self.volume_slider.valueChanged.connect(self._on_volume_changed)

        # Playlist double-click to play
        self.playlist_widget.itemDoubleClicked.connect(self._on_playlist_double_clicked)

        # Table double-click: add to playlist and play immediately
        self.table.cellDoubleClicked.connect(self._on_table_double_clicked)

    def _setup_table(self) -> None:
        """Apply column resize modes, set initial widths, and set up context menus.

        Column order: 파일명(0) 경로(1) 아티스트(2) 제목(3) 앨범(4)
                      장르(5) 년도(6) 길이(7) 크기(8) 생성일시(9) 수정일시(10)
        """
        hdr = self.table.horizontalHeader()
        # Stretch columns fill available space
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        # Fixed-width columns are still user-resizable
        for col in (2, 4, 5, 6, 7, 8, 9, 10):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionsMovable(True)
        hdr.sectionMoved.connect(self._save_column_order)
        hdr.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hdr.customContextMenuRequested.connect(self._on_column_visibility_menu)
        self.table.setSortingEnabled(True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        # Lazy album-art tooltip: only load art when the mouse enters a cell
        self.table.viewport().installEventFilter(self)
        # Enable drag from table for playlist
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(self.table.DragDropMode.DragOnly)
        # Initial pixel widths for non-stretch columns
        self.table.setColumnWidth(2,  150)   # 아티스트
        self.table.setColumnWidth(4,  130)   # 앨범
        self.table.setColumnWidth(5,   70)   # 장르
        self.table.setColumnWidth(6,   50)   # 년도
        self.table.setColumnWidth(7,   55)   # 길이
        self.table.setColumnWidth(8,   90)   # 크기
        self.table.setColumnWidth(9,  130)   # 생성일시
        self.table.setColumnWidth(10, 130)   # 수정일시
        self._restore_column_order()
        self._restore_column_visibility()

    def _setup_playlist(self) -> None:
        """Configure the playlist widget to accept drops from the MP3 table."""
        self.playlist_widget.setAcceptDrops(True)
        self.playlist_widget.setDropIndicatorShown(True)
        # Override drop handling via event filter
        self.playlist_widget.viewport().installEventFilter(self)

    def _restore_path(self) -> None:
        """Load the last-used directory path from QSettings and display it."""
        saved = self._settings.value(_KEY_LAST_PATH, "")
        if saved:
            self.path_edit.setText(saved)

    # ------------------------------------------------------------------
    # Qt event filter: handle drag-and-drop onto playlist
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        """
        Intercept drag-and-drop events on the playlist viewport.

        Accepts text/uri-list drags from the MP3 table and adds the
        corresponding file path to the playlist.

        Args:
            obj:   The watched object (playlist viewport).
            event: The Qt event.

        Returns:
            True if the event was handled, False to pass it on.
        """
        from PyQt6.QtCore import QEvent
        # Lazy album-art tooltip for the MP3 table
        if obj is self.table.viewport() and event.type() == QEvent.Type.ToolTip:
            pos = event.pos()
            index = self.table.indexAt(pos)
            if index.isValid() and index.column() == 0:
                item = self.table.item(index.row(), 0)
                if item and not item.toolTip():
                    path = item.data(Qt.ItemDataRole.UserRole)
                    item.setToolTip(_album_art_tooltip(path))
            return False  # let Qt show the tooltip normally

        if obj is self.playlist_widget.viewport():
            if event.type() == QEvent.Type.DragEnter:
                if event.mimeData().hasUrls() or event.mimeData().hasText():
                    event.acceptProposedAction()
                    return True
            elif event.type() == QEvent.Type.Drop:
                mime = event.mimeData()
                paths = []
                if mime.hasUrls():
                    paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
                elif mime.hasText():
                    paths = [p for p in mime.text().splitlines() if p.strip()]
                for path in paths:
                    self._playlist_add(path)
                event.acceptProposedAction()
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Playlist helpers
    # ------------------------------------------------------------------

    def _playlist_add(self, path: str) -> None:
        """
        Append a file path to the playlist widget.

        Duplicate entries are allowed so the same track can appear
        multiple times in the playlist.

        Args:
            path: Absolute path of the audio file to add.
        """
        display = os.path.basename(path)
        item = QListWidgetItem(display)
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        self.playlist_widget.addItem(item)

    def _playlist_current_path(self) -> str | None:
        """Return the file path of the currently selected playlist item, or None."""
        item = self.playlist_widget.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _playlist_play_index(self, index: int) -> None:
        """
        Select the playlist item at *index* and start playback.

        Args:
            index: Row index in the playlist widget.
        """
        if index < 0 or index >= self.playlist_widget.count():
            return
        self.playlist_widget.setCurrentRow(index)
        path = self.playlist_widget.item(index).data(Qt.ItemDataRole.UserRole)
        self._play_path(path)

    def _play_path(self, path: str) -> None:
        """
        Load *path* into the media player and begin playback.

        Does nothing when QtMultimedia is unavailable.

        Args:
            path: Absolute path to the audio file.
        """
        name = os.path.basename(path)
        self.player_title_label.setText(name)
        if self._player is None:
            return
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    # ------------------------------------------------------------------
    # Playback slots
    # ------------------------------------------------------------------

    def _on_play_pause_clicked(self) -> None:
        """Toggle between play and pause; start first playlist item if idle."""
        if self._player is None:
            return
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self._player.play()
        else:
            # Stopped or no source — play selected or first item
            idx = self.playlist_widget.currentRow()
            if idx < 0 and self.playlist_widget.count() > 0:
                idx = 0
            if idx >= 0:
                self._playlist_play_index(idx)

    def _on_stop_clicked(self) -> None:
        """Stop playback and reset the seek slider."""
        if self._player is not None:
            self._player.stop()

    def _on_prev_clicked(self) -> None:
        """Play the previous item in the playlist."""
        idx = self.playlist_widget.currentRow()
        self._playlist_play_index(max(0, idx - 1))

    def _on_next_clicked(self) -> None:
        """Play the next item in the playlist."""
        idx = self.playlist_widget.currentRow()
        self._playlist_play_index(idx + 1)

    def _on_playlist_save_clicked(self) -> None:
        """
        Prompt for a playlist name and save current entries to a .list file.

        Each line in the file contains the absolute path of one track.
        Does nothing when the playlist is empty.
        """
        if self.playlist_widget.count() == 0:
            QMessageBox.information(self, "알림", "재생 목록이 비어 있습니다.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "재생 목록 저장", "", "재생 목록 (*.list)"
        )
        if not path:
            return
        if not path.endswith(".list"):
            path += ".list"

        with open(path, "w", encoding="utf-8") as f:
            for i in range(self.playlist_widget.count()):
                f.write(self.playlist_widget.item(i).data(Qt.ItemDataRole.UserRole) + "\n")

    def _on_playlist_load_clicked(self) -> None:
        """
        Open a .list file and append its tracks to the current playlist.

        Missing files are silently skipped.
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "재생 목록 불러오기", "", "재생 목록 (*.list)"
        )
        if not path:
            return

        with open(path, "r", encoding="utf-8") as f:
            lines = [l.rstrip("\n") for l in f if l.strip()]

        skipped = 0
        for file_path in lines:
            if os.path.isfile(file_path):
                self._playlist_add(file_path)
            else:
                skipped += 1

        if skipped:
            QMessageBox.warning(
                self, "경고",
                f"{skipped}개 파일을 찾을 수 없어 건너뛰었습니다."
            )

    def _on_play_mode_clicked(self) -> None:
        """
        Cycle through playback modes in order:
        sequential → repeat_one → repeat_all → shuffle → sequential …

        Updates the button label to reflect the active mode.
        """
        _modes = [
            ("sequential",  "➡ 전체재생"),
            ("repeat_one",  "🔂 한곡반복"),
            ("repeat_all",  "🔁 전체반복"),
            ("shuffle",     "🔀 랜덤"),
        ]
        keys = [m[0] for m in _modes]
        idx = (keys.index(self._play_mode) + 1) % len(_modes)
        self._play_mode = _modes[idx][0]
        self.btn_play_mode.setText(_modes[idx][1])

    def _on_playlist_clear_clicked(self) -> None:
        """Stop playback and remove all items from the playlist."""
        if self._player is not None:
            self._player.stop()
        self.playlist_widget.clear()
        self.player_title_label.setText("-")
        self.time_current_label.setText("0:00")
        self.time_total_label.setText("0:00")
        self.seek_slider.setValue(0)

    def _on_playlist_double_clicked(self, item: QListWidgetItem) -> None:
        """
        Start playback of the double-clicked playlist item.

        Args:
            item: The list widget item that was double-clicked.
        """
        path = item.data(Qt.ItemDataRole.UserRole)
        self._play_path(path)

    def _on_table_double_clicked(self, row: int, _col: int) -> None:
        """
        Add the double-clicked table row to the playlist and play it immediately.

        If the file is already in the playlist its existing entry is reused;
        otherwise it is appended.  Playback starts right away.

        Args:
            row:  Row index that was double-clicked.
            _col: Column index (ignored).
        """
        path = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self._playlist_add(path)
        # Play the item just appended (always the last one added)
        self._playlist_play_index(self.playlist_widget.count() - 1)

    # ------------------------------------------------------------------
    # Media player signal handlers
    # ------------------------------------------------------------------

    def _on_position_changed(self, position: int) -> None:
        """
        Update the seek slider and current time label as the track plays.

        Args:
            position: Current playback position in milliseconds.
        """
        if not self._seeking:
            duration = self._player.duration()
            if duration > 0:
                self.seek_slider.setValue(int(position * 1000 / duration))
        self.time_current_label.setText(_fmt_ms(position))

    def _on_duration_changed(self, duration: int) -> None:
        """
        Update the total time label when a new track is loaded.

        Args:
            duration: Total track duration in milliseconds.
        """
        self.time_total_label.setText(_fmt_ms(duration))

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        """
        Update the play/pause button icon to reflect current playback state.

        Args:
            state: New playback state.
        """
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play_pause.setText("⏸")
        else:
            self.btn_play_pause.setText("▶")

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        """
        Handle end-of-track according to the current playback mode.

        Modes:
          sequential  – advance to next; stop after last track
          repeat_one  – replay the same track
          repeat_all  – advance to next; wrap around to first after last
          shuffle     – pick a random track from the playlist

        Args:
            status: New media status from QMediaPlayer.
        """
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return

        count = self.playlist_widget.count()
        if count == 0:
            return

        idx = self.playlist_widget.currentRow()

        if self._play_mode == "repeat_one":
            self._playlist_play_index(idx)

        elif self._play_mode == "repeat_all":
            self._playlist_play_index((idx + 1) % count)

        elif self._play_mode == "shuffle":
            import random
            self._playlist_play_index(random.randrange(count))

        else:  # sequential
            next_idx = idx + 1
            if next_idx < count:
                self._playlist_play_index(next_idx)
            else:
                self.seek_slider.setValue(0)
                self.btn_play_pause.setText("▶")

    def _on_volume_changed(self, value: int) -> None:
        """
        Apply the slider value as the audio output volume.

        Args:
            value: Integer in 0–100 range from the volume_slider.
        """
        self.volume_label.setText(str(value))
        if self._audio_output is not None:
            self._audio_output.setVolume(value / 100.0)

    def _on_seek_slider_pressed(self) -> None:
        """Mark that the user is dragging the seek slider."""
        self._seeking = True

    def _on_seek_slider_released(self) -> None:
        """Seek to the slider position when the user releases the handle."""
        self._seeking = False
        if self._player is None:
            return
        duration = self._player.duration()
        if duration > 0:
            pos = int(self.seek_slider.value() * duration / 1000)
            self._player.setPosition(pos)

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
        action_playlist = menu.addAction("재생 목록에 추가")
        menu.addSeparator()
        action_info   = menu.addAction("인터넷에서 정보 보기")
        action_tag    = menu.addAction("태그 찾기")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))

        if action == action_detail:
            dlg = TagDetailDialog(file_info, manager=self._manager, parent=self)
            dlg.exec()
            self._load_table()
        elif action == action_playlist:
            self._playlist_add(path)
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
            # Tooltip is populated lazily on hover via _on_table_tooltip

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
            self.table.setItem(row, 2, _item(f["artist"] or "-"))
            self.table.setItem(row, 3, _item(f["title"] or "-"))
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

    def _save_column_order(self) -> None:
        """Persist the current visual column order to QSettings."""
        hdr = self.table.horizontalHeader()
        order = [hdr.logicalIndex(vi) for vi in range(hdr.count())]
        self._settings.setValue("table/column_order", order)

    def _restore_column_order(self) -> None:
        """Restore the saved visual column order from QSettings."""
        order = self._settings.value("table/column_order", [])
        if isinstance(order, str):
            order = [order]
        if not order:
            return
        hdr = self.table.horizontalHeader()
        for visual_idx, logical_idx in enumerate(order):
            current_visual = hdr.visualIndex(int(logical_idx))
            if current_visual != visual_idx:
                hdr.moveSection(current_visual, visual_idx)

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
        """Close the database connection and stop media player when the window is closed."""
        if self._player is not None:
            self._player.stop()
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
