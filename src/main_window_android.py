"""
main_window_android.py - KivyMD UI for the MP3 archive manager (Android).

Provides a Material Design interface split into two bottom-navigation tabs:
  - "목록" (List): pick a directory with the in-app file manager, scan it
    into the database, browse the stored MP3 records, and select rows to
    delete.
  - "재생" (Player): play a tapped track with play/pause and stop controls
    and a position indicator, backed by kivy.core.audio.SoundLoader.

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
from kivy.core.audio import SoundLoader
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty

from kivymd.app import MDApp
from kivymd.uix.bottomnavigation import MDBottomNavigation
from kivymd.uix.button import MDIconButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.filemanager import MDFileManager
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
    on_release: app.play_row(root)
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

    MDBottomNavigation:
        id: bottom_nav

        MDBottomNavigationItem:
            name: "list"
            text: "목록"
            icon: "format-list-bulleted"

            MDBoxLayout:
                orientation: "vertical"

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

        MDBottomNavigationItem:
            name: "player"
            text: "재생"
            icon: "play-circle"

            MDBoxLayout:
                orientation: "vertical"
                padding: dp(16)
                spacing: dp(12)

                Widget:

                MDLabel:
                    id: now_playing
                    text: "재생 중인 곡이 없습니다"
                    halign: "center"
                    font_style: "H6"
                    size_hint_y: None
                    height: dp(36)

                MDLabel:
                    id: now_playing_sub
                    text: ""
                    halign: "center"
                    font_style: "Caption"
                    theme_text_color: "Secondary"
                    size_hint_y: None
                    height: dp(20)

                MDProgressBar:
                    id: position_bar
                    value: 0
                    max: 100
                    size_hint_y: None
                    height: dp(4)

                MDBoxLayout:
                    size_hint_y: None
                    height: dp(20)

                    MDLabel:
                        id: pos_label
                        text: "0:00"
                        font_style: "Caption"
                        theme_text_color: "Secondary"

                    MDLabel:
                        id: dur_label
                        text: "0:00"
                        halign: "right"
                        font_style: "Caption"
                        theme_text_color: "Secondary"

                MDBoxLayout:
                    size_hint_y: None
                    height: dp(72)
                    spacing: dp(24)

                    Widget:

                    MDIconButton:
                        id: play_button
                        icon: "play"
                        pos_hint: {"center_y": 0.5}
                        on_release: app.toggle_play_pause()

                    MDIconButton:
                        icon: "stop"
                        pos_hint: {"center_y": 0.5}
                        on_release: app.stop_playback()

                    Widget:

                Widget:
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
        """Initialise the app, open the SQLite database, and reset player state."""
        super().__init__(**kwargs)
        db_path = os.path.join(self._storage_directory(), "mp3_archive.db")
        self._manager = Mp3Manager(db_path)
        self._selected: set[str] = set()   # selected file paths

        # Playback state (재생 tab)
        self._sound = None             # current kivy Sound, or None
        self._paused_pos = 0.0         # remembered position for pause/resume (s)
        self._pos_event = None         # Clock event polling playback position

        # Folder picker (MDFileManager) state
        self._file_manager = None      # lazily-created MDFileManager
        self._fm_open = False          # whether the file manager is showing

    # ------------------------------------------------------------------
    # Kivy lifecycle
    # ------------------------------------------------------------------

    def build(self):
        """Build the UI from the KV string, registering a Korean font first."""
        self._register_fonts()
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.theme_style = "Light"
        root = Builder.load_string(KV)
        Window.bind(on_keyboard=self._on_keyboard)
        return root

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
        """Stop playback and close the database connection when the app exits."""
        self._stop_sound()
        self._manager.close()

    # ------------------------------------------------------------------
    # Folder picking
    # ------------------------------------------------------------------

    def open_folder_picker(self) -> None:
        """
        Let the user pick a directory to scan via the in-app file manager.

        On Android 11+ a directory scan needs "All files access"
        (MANAGE_EXTERNAL_STORAGE); if it has not been granted, send the user
        to the system settings page to grant it and ask them to retry.
        """
        if not self._has_all_files_access():
            self._request_all_files_access()
            Snackbar(text="'모든 파일 접근'을 허용한 뒤 다시 폴더를 선택하세요.").open()
            return
        self._show_file_manager()

    def _show_file_manager(self) -> None:
        """Open MDFileManager rooted at external storage, in folder-select mode."""
        try:
            if self._file_manager is None:
                self._file_manager = MDFileManager(
                    select_path=self._on_dir_selected,
                    exit_manager=self._close_file_manager,
                    selector="folder",
                )
            self._fm_open = True
            self._file_manager.show(self._storage_root())
        except Exception:
            # If the manager cannot open, fall back to the default music dir.
            self._fm_open = False
            Snackbar(text="파일 관리자를 열 수 없어 /sdcard/Music을 스캔합니다.").open()
            self._start_scan("/sdcard/Music")

    def _on_dir_selected(self, path: str) -> None:
        """
        Handle a directory chosen in the file manager: close it and scan.

        Args:
            path: The selected directory path.
        """
        self._close_file_manager()
        self._start_scan(path)

    def _close_file_manager(self, *args) -> None:
        """Close the file manager if it is open."""
        self._fm_open = False
        if self._file_manager is not None:
            self._file_manager.close()

    def _on_keyboard(self, _window, key, *args) -> bool:
        """
        Route the Android back button to closing the file manager.

        Args:
            _window: The Window instance (unused).
            key:     Key code; 27 is the Android back button.

        Returns:
            True if the press was consumed (manager was open), else False.
        """
        if key == 27 and self._fm_open:
            self._close_file_manager()
            return True
        return False

    @staticmethod
    def _storage_root(exists=os.path.exists) -> str:
        """
        Return the external-storage root to start the file manager from.

        Args:
            exists: Predicate to test path existence; injectable for tests.

        Returns:
            "/storage/emulated/0" or "/sdcard" if present, else the home dir.
        """
        for path in ("/storage/emulated/0", "/sdcard"):
            if exists(path):
                return path
        return os.path.expanduser("~")

    @staticmethod
    def _has_all_files_access() -> bool:
        """
        Return whether the app may read all of shared storage.

        On Android 11+ (API 30+), browsing and scanning arbitrary directories
        requires MANAGE_EXTERNAL_STORAGE. Returns True off-device or when the
        check is unavailable, so desktop and tests are never blocked.
        """
        try:
            from jnius import autoclass  # type: ignore
            version = autoclass("android.os.Build$VERSION")
            if version.SDK_INT < 30:
                return True
            environment = autoclass("android.os.Environment")
            return bool(environment.isExternalStorageManager())
        except Exception:
            return True

    @staticmethod
    def _request_all_files_access() -> None:
        """
        Open the system "All files access" settings page for this app.

        No-op off-device or when the required Android classes are unavailable.
        """
        try:
            from jnius import autoclass  # type: ignore
            version = autoclass("android.os.Build$VERSION")
            if version.SDK_INT < 30:
                return
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            Settings = autoclass("android.provider.Settings")
            Uri = autoclass("android.net.Uri")
            activity = PythonActivity.mActivity
            intent = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
            intent.setData(Uri.parse("package:" + activity.getPackageName()))
            activity.startActivity(intent)
        except Exception:
            pass

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
    # Playback (재생 tab)
    # ------------------------------------------------------------------

    def play_row(self, row: "Mp3Row") -> None:
        """
        Play the track for a tapped list row and switch to the player tab.

        Tapping the row body plays; tapping the row's right icon selects it
        for deletion (see toggle_select).

        Args:
            row: The Mp3Row whose audio file should be played.
        """
        if not row.path:
            return
        self._play(row.path, row.filename, f"{row.artist} — {row.title}")
        try:
            self.root.ids.bottom_nav.switch_tab("player")
        except Exception:
            pass  # tab switch is best-effort; playback already started

    def _play(self, path: str, title: str, subtitle: str) -> None:
        """
        Load and start playing an audio file, updating the player UI.

        Any currently playing sound is stopped and unloaded first. On load
        failure a Snackbar is shown and the player state is left cleared.

        Args:
            path:     Absolute path to the audio file.
            title:    Primary label text (typically the filename).
            subtitle: Secondary label text (typically "artist — title").
        """
        self._stop_sound()
        sound = SoundLoader.load(path)
        if sound is None:
            Snackbar(text="이 파일을 재생할 수 없습니다.").open()
            return
        self._sound = sound
        self._paused_pos = 0.0
        self.root.ids.now_playing.text = title
        self.root.ids.now_playing_sub.text = subtitle
        self.root.ids.position_bar.value = 0
        sound.play()
        self.root.ids.play_button.icon = "pause"
        self._schedule_pos()

    def toggle_play_pause(self) -> None:
        """
        Toggle between playing and paused for the current track.

        Kivy's Sound has no pause, so pausing remembers get_pos() and stops;
        resuming plays and seeks back to the remembered position.
        """
        sound = self._sound
        if sound is None:
            Snackbar(text="재생할 곡을 목록에서 선택하세요.").open()
            return
        if sound.state == "play":
            self._paused_pos = sound.get_pos() or 0.0
            sound.stop()
            self.root.ids.play_button.icon = "play"
            self._unschedule_pos()
        else:
            sound.play()
            if self._paused_pos:
                sound.seek(self._paused_pos)
            self.root.ids.play_button.icon = "pause"
            self._schedule_pos()

    def stop_playback(self) -> None:
        """Stop playback, unload the sound, and reset the player controls."""
        self._stop_sound()
        self._paused_pos = 0.0
        self.root.ids.play_button.icon = "play"
        self.root.ids.position_bar.value = 0
        self.root.ids.pos_label.text = self._format_time(0)
        self.root.ids.dur_label.text = self._format_time(0)

    def _stop_sound(self) -> None:
        """Stop and unload the current sound and cancel position polling."""
        self._unschedule_pos()
        if self._sound is not None:
            try:
                self._sound.stop()
                self._sound.unload()
            except Exception:
                pass  # provider may already have released the sound
            self._sound = None

    def _schedule_pos(self) -> None:
        """Start polling playback position every 0.5 s."""
        self._unschedule_pos()
        self._pos_event = Clock.schedule_interval(self._update_position, 0.5)

    def _unschedule_pos(self) -> None:
        """Cancel the playback-position polling event if active."""
        if self._pos_event is not None:
            self._pos_event.cancel()
            self._pos_event = None

    def _update_position(self, _dt: float) -> bool:
        """
        Refresh the position bar and time labels from the playing sound.

        Args:
            _dt: Elapsed time since the last call (unused; required by Clock).

        Returns:
            False to unschedule when playback has ended or stopped, else None.
        """
        sound = self._sound
        if sound is None:
            return False
        if sound.state != "play":
            # Reached the end (or stopped externally): reset the controls.
            self.stop_playback()
            return False
        length = sound.length or 0
        pos = sound.get_pos() or 0
        self.root.ids.position_bar.value = (pos / length * 100) if length else 0
        self.root.ids.pos_label.text = self._format_time(pos)
        self.root.ids.dur_label.text = self._format_time(length)

    @staticmethod
    def _format_time(seconds) -> str:
        """
        Format a number of seconds as 'm:ss' (e.g. 95 -> '1:35').

        Args:
            seconds: A duration in seconds; None or non-numeric is treated as 0.

        Returns:
            A 'm:ss' string with a zero-padded seconds field.
        """
        try:
            total = int(seconds)
        except (TypeError, ValueError):
            total = 0
        if total < 0:
            total = 0
        return f"{total // 60}:{total % 60:02d}"

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
