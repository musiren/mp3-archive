"""
main_window_android.py - KivyMD UI for the MP3 archive manager (Android).

Provides a Material Design interface with:
  - Storage directory scan via Android file chooser (plyer)
  - Progress bar updated during background scan
  - Scrollable list of stored MP3 records
  - Swipe-to-delete or toolbar delete for selected items

Requirements:
    pip install kivy kivymd plyer mutagen

Buildozer requirements line:
    requirements = python3,kivy,kivymd,plyer,mutagen,sqlite3

Entry point for buildozer:
    Set 'main = main_window_android.py' in mp3-archive-android.spec
"""

import os
import threading

from kivy.clock import Clock, mainthread
from kivy.core.text import LabelBase
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import BooleanProperty, StringProperty

from kivymd.app import MDApp
from kivymd.uix.button import MDIconButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.list import TwoLineAvatarIconListItem, IconRightWidget
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.snackbar import Snackbar
from kivymd.uix.toolbar import MDTopAppBar

from mp3_manager import Mp3Manager


# Android system fonts that include Korean (Hangul) glyphs, in preference
# order. The first that exists on the device is registered as the default
# 'Roboto' font so the UI's Korean strings render instead of tofu boxes.
_KOREAN_FONT_CANDIDATES = (
    "/system/fonts/NotoSansCJK-Regular.ttc",
    "/system/fonts/NotoSansKR-Regular.otf",
    "/system/fonts/NotoSansKR-Regular.ttf",
    "/system/fonts/NotoSansCJKkr-Regular.otf",
    "/system/fonts/SECCJK-Regular.ttc",
    "/system/fonts/SamsungKorean-Regular.ttf",
    "/system/fonts/DroidSansFallback.ttf",
)


# ---------------------------------------------------------------------------
# KV layout string
# ---------------------------------------------------------------------------

KV = """
<Mp3Row>:
    text: root.filename
    secondary_text: root.artist + " — " + root.title
    on_release: app.toggle_select(root)
    IconRightWidget:
        icon: "check-circle" if root.selected else "circle-outline"
        theme_text_color: "Custom"
        text_color: app.theme_cls.primary_color if root.selected else (0.6, 0.6, 0.6, 1)
        on_release: app.toggle_select(root)

MDBoxLayout:
    orientation: "vertical"
    md_bg_color: app.theme_cls.bg_normal

    MDTopAppBar:
        id: toolbar
        title: "MP3 Archive"
        elevation: 4
        right_action_items: [["folder-search", lambda x: app.open_folder_picker()], ["delete", lambda x: app.delete_selected()]]

    MDProgressBar:
        id: progress_bar
        value: 0
        max: 100
        size_hint_y: None
        height: dp(4)
        opacity: 0

    MDLabel:
        id: status_label
        text: "준비"
        halign: "center"
        size_hint_y: None
        height: dp(24)
        font_style: "Caption"
        theme_text_color: "Secondary"

    ScrollView:
        MDList:
            id: mp3_list
            size_hint_y: None
            height: self.minimum_height
"""


# ---------------------------------------------------------------------------
# List item widget
# ---------------------------------------------------------------------------

class Mp3Row(TwoLineAvatarIconListItem):
    """
    A single row in the MP3 list.

    Displays filename, artist, and title with a selection indicator icon.
    """

    filename = StringProperty("")
    artist   = StringProperty("")
    title    = StringProperty("")
    path     = StringProperty("")
    selected = BooleanProperty(False)


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class Mp3ArchiveApp(MDApp):
    """
    KivyMD application for browsing and managing MP3 files on Android.

    Manages a Mp3Manager instance and drives the UI from a background
    scan thread, posting updates to the main thread via Clock.schedule_once.
    """

    def __init__(self, **kwargs) -> None:
        """Initialise the app and open the SQLite database."""
        super().__init__(**kwargs)
        db_path = os.path.join(self._storage_directory(), "mp3_archive.db")
        self._manager = Mp3Manager(db_path)
        self._selected: set[str] = set()   # selected file paths

    # ------------------------------------------------------------------
    # Kivy lifecycle
    # ------------------------------------------------------------------

    def build(self):
        """Build the UI from the KV string, registering a Korean font first."""
        self._register_fonts()
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.theme_style = "Light"
        return Builder.load_string(KV)

    def on_start(self) -> None:
        """Request storage permissions and populate the list at startup."""
        self._request_android_permissions()
        self._refresh_list()

    def _register_fonts(self) -> None:
        """
        Register a Korean-capable font as the default so Hangul renders.

        Kivy and KivyMD default to the 'Roboto' font, which has no CJK glyphs,
        so Korean text renders as empty tofu boxes. Re-registering the 'Roboto'
        name to point at an Android system CJK font makes every default-styled
        label render Hangul. No-op on platforms where no candidate font exists
        (e.g. desktop), leaving the bundled Roboto in place.
        """
        font_path = self._find_korean_font()
        if font_path:
            LabelBase.register(name="Roboto", fn_regular=font_path)

    @staticmethod
    def _request_android_permissions() -> None:
        """
        Request runtime storage permissions on Android (no-op off-device).

        Declaring permissions in the manifest is not sufficient on Android 6+
        (API 23+); they must also be granted at runtime or directory scans
        silently return zero files. The android module is imported lazily so
        the method is a harmless no-op on desktop.
        """
        try:
            from android.permissions import request_permissions, Permission  # type: ignore
        except ImportError:
            return
        names = ("READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE", "READ_MEDIA_AUDIO")
        perms = [getattr(Permission, n) for n in names if hasattr(Permission, n)]
        if perms:
            request_permissions(perms)

    def on_stop(self) -> None:
        """Close the database connection when the app exits."""
        self._manager.close()

    # ------------------------------------------------------------------
    # Folder picking
    # ------------------------------------------------------------------

    def open_folder_picker(self) -> None:
        """
        Open the Android file chooser to select a music directory.

        Falls back to /sdcard/Music if plyer is unavailable.
        """
        try:
            from plyer import filechooser
            filechooser.open_file(
                on_selection=self._on_folder_selected,
                filters=[],
                multiple=False,
                preview=False,
                title="Select music folder",
                path="/sdcard/Music",
            )
        except Exception:
            # Fallback: scan the default music directory directly
            self._start_scan("/sdcard/Music")

    def _on_folder_selected(self, selection: list) -> None:
        """
        Handle the folder selection result from the file chooser.

        Args:
            selection: List of selected paths (first element is used).
        """
        if not selection:
            return
        path = selection[0]
        directory = path if os.path.isdir(path) else os.path.dirname(path)
        self._start_scan(directory)

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _start_scan(self, directory: str) -> None:
        """
        Launch a background thread to scan the given directory.

        Args:
            directory: Root path to scan for MP3 files.
        """
        self._set_status(f"스캔 중: {os.path.basename(directory)}")
        self._set_progress_visible(True)
        self._set_progress(0)
        thread = threading.Thread(
            target=self._scan_worker,
            args=(directory,),
            daemon=True,
        )
        thread.start()

    def _scan_worker(self, directory: str) -> None:
        """
        Run Mp3Manager.scan() in a background thread and post UI updates.

        Args:
            directory: Directory path passed to Mp3Manager.scan().
        """
        def on_progress(current: int, total: int, path: str) -> None:
            """Schedule a progress bar update on the main thread."""
            pct = int(current / total * 100) if total else 0
            Clock.schedule_once(lambda dt: self._set_progress(pct))

        result = self._manager.scan(directory, progress_callback=on_progress)
        Clock.schedule_once(lambda dt: self._on_scan_done(result))

    @mainthread
    def _on_scan_done(self, result: tuple) -> None:
        """
        Refresh the list and reset the UI after a scan completes.

        Args:
            result: The (processed, skipped, removed) tuple returned by
                    Mp3Manager.scan().
        """
        self._set_progress_visible(False)
        self._set_status(self._format_scan_summary(*result))
        self._refresh_list()

    @staticmethod
    def _format_scan_summary(processed: int, skipped: int, removed: int) -> str:
        """
        Build a Korean status message summarising a scan result.

        Args:
            processed: Number of files newly read and saved.
            skipped:   Number of unchanged files skipped.
            removed:   Number of stale records removed.

        Returns:
            A human-readable summary string (never a raw tuple).
        """
        return f"완료: 추가 {processed} · 건너뜀 {skipped} · 삭제 {removed}"

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _refresh_list(self) -> None:
        """Clear and repopulate the MP3 list from the database."""
        mp3_list = self.root.ids.mp3_list
        mp3_list.clear_widgets()
        self._selected.clear()

        for f in self._manager.list_files():
            row = Mp3Row(
                filename=f["filename"],
                artist=f["artist"] or "-",
                title=f["title"] or "-",
                path=f["path"],
            )
            mp3_list.add_widget(row)

    def toggle_select(self, row: Mp3Row) -> None:
        """
        Toggle the selection state of a list row.

        Args:
            row: The Mp3Row widget that was tapped.
        """
        if row.path in self._selected:
            self._selected.discard(row.path)
            row.selected = False
        else:
            self._selected.add(row.path)
            row.selected = True

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_selected(self) -> None:
        """Show a confirmation dialog before deleting selected records."""
        if not self._selected:
            Snackbar(text="삭제할 항목을 선택해주세요.").open()
            return

        count = len(self._selected)
        self._confirm_dialog = MDDialog(
            title="삭제 확인",
            text=f"선택한 {count}개 항목을 삭제할까요?",
            buttons=[
                MDIconButton(
                    icon="close",
                    on_release=lambda x: self._confirm_dialog.dismiss(),
                ),
                MDIconButton(
                    icon="check",
                    on_release=lambda x: self._do_delete(),
                ),
            ],
        )
        self._confirm_dialog.open()

    def _do_delete(self) -> None:
        """Delete all selected records from the database and refresh."""
        self._confirm_dialog.dismiss()
        for path in list(self._selected):
            self._manager.delete(path)
        count = len(self._selected)
        self._refresh_list()
        Snackbar(text=f"{count}개 항목이 삭제되었습니다.").open()

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        """
        Update the status label text.

        Args:
            text: Message to display below the progress bar.
        """
        self.root.ids.status_label.text = text

    def _set_progress(self, value: int) -> None:
        """
        Set the progress bar value (0–100).

        Args:
            value: Progress percentage.
        """
        self.root.ids.progress_bar.value = value

    def _set_progress_visible(self, visible: bool) -> None:
        """
        Show or hide the progress bar.

        Args:
            visible: True to show, False to hide.
        """
        self.root.ids.progress_bar.opacity = 1 if visible else 0

    @staticmethod
    def _find_korean_font(exists=os.path.exists) -> str | None:
        """
        Return the first available Korean-capable system font path, or None.

        Args:
            exists: Predicate used to test a path's existence; injectable so
                    tests can simulate device font layouts without a device.

        Returns:
            The first existing path from _KOREAN_FONT_CANDIDATES, or None when
            none of the candidates are present (e.g. on desktop).
        """
        for path in _KOREAN_FONT_CANDIDATES:
            if exists(path):
                return path
        return None

    @staticmethod
    def _storage_directory() -> str:
        """
        Return a writable directory for the database file.

        Uses the app's private storage on Android, or the current
        working directory on desktop.

        Note: must not be named ``_app_directory`` — Kivy's ``App.__init__``
        sets an instance attribute ``self._app_directory = None`` (backing the
        ``App.directory`` property), which would shadow this static method and
        make ``self._app_directory()`` raise ``'NoneType' object is not
        callable`` at startup.
        """
        try:
            from android.storage import app_storage_path  # type: ignore
            return app_storage_path()
        except ImportError:
            return os.getcwd()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    Mp3ArchiveApp().run()
