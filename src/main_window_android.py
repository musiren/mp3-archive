"""
main_window_android.py - KivyMD UI for the MP3 archive manager (Android).

Provides a Material Design interface split into two bottom-navigation tabs:
  - "목록" (List): pick a directory with the in-app file manager, scan it
    (incremental or full rescan), search by filename or tags, browse the
    stored MP3 records, select rows to delete, and long-press a row to view
    or edit its tags (자세히) or read its lyrics (가사).
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
from kivy.factory import Factory
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recyclegridlayout import RecycleGridLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.scrollview import ScrollView

from kivymd.app import MDApp
from kivymd.uix.behaviors import TouchBehavior
from kivymd.uix.bottomnavigation import MDBottomNavigation
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton, MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.filemanager import MDFileManager
from kivymd.uix.label import MDLabel
from kivymd.uix.list import (
    IconRightWidget,
    ImageLeftWidget,
    OneLineAvatarIconListItem,
    OneLineListItem,
    TwoLineAvatarIconListItem,
)
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.snackbar import MDSnackbar
from kivymd.uix.textfield import MDTextField
from kivymd.uix.toolbar import MDTopAppBar

from audio_meta import get_album_art, get_lyrics, to_easy_tags
import itunes_fetcher
import mb_fetcher
from mp3_manager import Mp3Manager
from online_meta import (
    SOURCE_BOTH,
    SOURCE_ITUNES,
    SOURCE_LABELS,
    SOURCE_MB,
    TagFetchQueue,
    build_song_query,
    fetch_candidates,
)
from tree_util import build_tree_rows


class Snackbar:
    """
    Compatibility shim for the removed KivyMD 1.1 ``Snackbar(text=...)`` API.

    KivyMD 1.2.0 dropped ``Snackbar``'s ``text`` property in favour of an
    ``MDSnackbar`` built from ``MDLabel`` children; the old call form crashed
    the app with a "Properties ['text'] ... may not be existing" error. This
    wraps the new API so existing ``Snackbar(text=msg).open()`` sites keep
    working and show a centred bottom snackbar.
    """

    def __init__(self, text: str = "") -> None:
        """Store the message to display when open() is called."""
        self._text = text

    def open(self) -> None:
        """
        Show the stored message using the KivyMD 1.2.0 MDSnackbar API.

        MDSnackbar.open() is a no-op while another MDSnackbar is still on
        screen (it lingers ~3 s), so dismiss any visible one first to ensure
        the latest message always appears.
        """
        try:
            from kivy.core.window import Window
            host = getattr(Window, "parent", None)
            if host is not None:
                for child in list(host.children):
                    if isinstance(child, MDSnackbar):
                        child.dismiss()
        except Exception:
            pass
        MDSnackbar(
            MDLabel(text=self._text, theme_text_color="Custom", text_color=(1, 1, 1, 1)),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.9,
        ).open()


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
<Mp3RowDetails>:
    text: root.filename
    secondary_text: root.artist + " — " + root.title
    on_release: app.play_row(root)
    ImageLeftWidget:
        source: root.art_source
    IconRightWidget:
        icon: "check-circle" if root.selected else "circle-outline"
        theme_text_color: "Custom"
        text_color: app.theme_cls.primary_color if root.selected else (0.6, 0.6, 0.6, 1)
        on_release: app.toggle_select(root)

<Mp3RowList>:
    text: root.filename
    on_release: app.play_row(root)
    IconRightWidget:
        icon: "check-circle" if root.selected else "circle-outline"
        theme_text_color: "Custom"
        text_color: app.theme_cls.primary_color if root.selected else (0.6, 0.6, 0.6, 1)
        on_release: app.toggle_select(root)

<Mp3TreeRow>:
    on_release: app.tree_row_tapped(root)

<Mp3Tile>:
    orientation: "vertical"
    padding: dp(4)
    spacing: dp(2)
    on_release: app.play_row(root)
    Image:
        source: root.art_source
        size_hint_y: None
        height: dp(116)
        allow_stretch: True
        keep_ratio: True
    MDLabel:
        text: root.filename
        font_style: "Caption"
        halign: "center"
        shorten: True
        shorten_from: "right"
        size_hint_y: None
        height: dp(36)

<LyricsContent>:
    orientation: "vertical"
    size_hint_y: None
    height: dp(360)

    ScrollView:
        MDLabel:
            id: lyrics_label
            text: ""
            size_hint_y: None
            height: self.texture_size[1]
            padding: dp(8), dp(8)

<TagEditContent>:
    orientation: "vertical"
    size_hint_y: None
    height: dp(420)

    ScrollView:
        MDBoxLayout:
            orientation: "vertical"
            spacing: dp(6)
            padding: dp(4)
            size_hint_y: None
            height: self.minimum_height

            Image:
                id: art_image
                source: ""
                size_hint_y: None
                height: dp(140)
                allow_stretch: True
                keep_ratio: True

            MDTextField:
                id: f_title
                hint_text: "제목"

            MDTextField:
                id: f_artist
                hint_text: "아티스트"

            MDTextField:
                id: f_album
                hint_text: "앨범"

            MDTextField:
                id: f_genre
                hint_text: "장르"

            MDTextField:
                id: f_year
                hint_text: "년도"

            MDTextField:
                id: f_comment
                hint_text: "코멘트"

<CandidateRow>:
    text: root.cand_title
    secondary_text: root.cand_sub
    on_release: app.select_candidate(root)
    IconRightWidget:
        icon: "check-circle" if root.selected else "circle-outline"
        theme_text_color: "Custom"
        text_color: app.theme_cls.primary_color if root.selected else (0.6, 0.6, 0.6, 1)
        on_release: app.select_candidate(root)

<SongInfoContent>:
    orientation: "vertical"
    spacing: dp(6)
    size_hint_y: None
    height: dp(580)

    MDLabel:
        id: si_header
        text: ""
        font_style: "Caption"
        theme_text_color: "Secondary"
        size_hint_y: None
        height: dp(48)

    MDBoxLayout:
        size_hint_y: None
        height: dp(56)
        spacing: dp(4)

        MDTextField:
            id: si_keyword
            hint_text: "검색어"

        MDFlatButton:
            id: si_source_btn
            text: "iTunes"
            size_hint_x: None
            width: dp(96)
            pos_hint: {"center_y": 0.5}
            on_release: app.open_source_menu()

        MDIconButton:
            icon: "magnify"
            pos_hint: {"center_y": 0.5}
            on_release: app.on_song_search()

    MDProgressBar:
        id: si_progress
        size_hint_y: None
        height: dp(4)
        opacity: 0

    MDLabel:
        id: si_status
        text: ""
        font_style: "Caption"
        halign: "center"
        size_hint_y: None
        height: dp(24)

    RecycleView:
        id: si_results
        viewclass: "CandidateRow"

        RecycleBoxLayout:
            orientation: "vertical"
            size_hint_y: None
            height: self.minimum_height
            default_size: None, dp(64)
            default_size_hint: 1, None

    ScrollView:
        size_hint_y: None
        height: dp(150)

        MDLabel:
            id: si_detail
            text: ""
            font_style: "Caption"
            theme_text_color: "Secondary"
            size_hint_y: None
            height: self.texture_size[1]
            text_size: self.width, None
            valign: "top"
            padding: dp(8), dp(4)

MDBoxLayout:
    orientation: "vertical"
    md_bg_color: app.theme_cls.bg_normal

    MDTopAppBar:
        id: toolbar
        title: "MP3 Archive"
        elevation: 4
        right_action_items: [["folder-search", lambda x: app.open_folder_picker()], ["refresh", lambda x: app.force_rescan()], ["view-list", lambda x: app.open_view_menu()], ["auto-fix", lambda x: app.start_batch_tag_fetch()], ["delete", lambda x: app.delete_selected()]]

    MDBottomNavigation:
        id: bottom_nav

        MDBottomNavigationItem:
            name: "list"
            text: "목록"
            icon: "format-list-bulleted"

            MDBoxLayout:
                orientation: "vertical"

                MDBoxLayout:
                    size_hint_y: None
                    height: dp(64)
                    padding: dp(8), 0
                    spacing: dp(4)

                    MDTextField:
                        id: search_field
                        hint_text: "검색 (제목·아티스트·파일명)"
                        on_text: app.on_search_text(self.text)

                    MDIconButton:
                        icon: "close"
                        pos_hint: {"center_y": 0.5}
                        on_release: app.clear_search()

                MDBoxLayout:
                    size_hint_y: None
                    height: dp(40)
                    padding: dp(8), 0

                    MDCheckbox:
                        id: chk_tags
                        size_hint_x: None
                        width: dp(40)
                        pos_hint: {"center_y": 0.5}
                        on_active: app.on_search_tags(self.active)

                    MDLabel:
                        text: "태그 포함"
                        font_style: "Caption"
                        pos_hint: {"center_y": 0.5}

                    Widget:

                    MDLabel:
                        id: count_label
                        text: "전체 0곡"
                        halign: "right"
                        font_style: "Caption"
                        theme_text_color: "Secondary"
                        pos_hint: {"center_y": 0.5}

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

                RecycleView:
                    id: mp3_list
                    viewclass: "Mp3RowDetails"

                    RecycleBoxLayout:
                        orientation: "vertical"
                        size_hint_y: None
                        height: self.minimum_height
                        default_size: None, dp(72)
                        default_size_hint: 1, None

                RecycleView:
                    id: mp3_grid
                    viewclass: "Mp3Tile"
                    size_hint_y: None
                    height: 0
                    opacity: 0

                    RecycleGridLayout:
                        cols: 3
                        size_hint_y: None
                        height: self.minimum_height
                        default_size: dp(124), dp(160)
                        default_size_hint: None, None
                        padding: dp(4)
                        spacing: dp(4)

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

def _open_actions_for(row) -> None:
    """
    Open the per-track actions menu for a long-pressed row.

    Sets a flag so the on_release that follows the long press does not also
    play the track (a long press fires both on_long_touch and the list item's
    on_release).
    """
    app = MDApp.get_running_app()
    if app is not None:
        app._suppress_next_play = True
        app.open_actions(row)


class Mp3RowDetails(RecycleDataViewBehavior, TwoLineAvatarIconListItem, TouchBehavior):
    """
    Two-line "자세히" row with an album-art thumbnail (a RecycleView viewclass).

    Only the rows on screen exist as widgets and are reused while scrolling, so
    the list stays fast for thousands of songs. Tap plays the track; tap the
    right icon selects it for deletion; a long-press opens the per-track
    actions menu (자세히 / 가사).
    """

    filename = StringProperty("")
    artist   = StringProperty("")
    title    = StringProperty("")
    path     = StringProperty("")
    selected = BooleanProperty(False)
    art_source = StringProperty("")   # album-art image path, "" when none
    index    = None

    def refresh_view_attrs(self, rv, index, data):
        """Record the index and lazily load this row's album art when (re)bound."""
        self.index = index
        result = super().refresh_view_attrs(rv, index, data)
        app = MDApp.get_running_app()
        self.art_source = app._album_source(self.path) if app else ""
        return result

    def on_long_touch(self, *args) -> None:
        """Open the per-track actions menu on a long press."""
        _open_actions_for(self)


class Mp3RowList(RecycleDataViewBehavior, OneLineAvatarIconListItem, TouchBehavior):
    """One-line "목록" row (compact); same gestures as Mp3RowDetails."""

    filename = StringProperty("")
    artist   = StringProperty("")
    title    = StringProperty("")
    path     = StringProperty("")
    selected = BooleanProperty(False)
    index    = None

    def refresh_view_attrs(self, rv, index, data):
        """Record the data index each time this recycled view is (re)bound."""
        self.index = index
        return super().refresh_view_attrs(rv, index, data)

    def on_long_touch(self, *args) -> None:
        """Open the per-track actions menu on a long press."""
        _open_actions_for(self)


class Mp3TreeRow(RecycleDataViewBehavior, OneLineListItem, TouchBehavior):
    """One-line folder/file row for the 트리 (tree) view (a RecycleView viewclass)."""

    is_dir = BooleanProperty(False)
    path   = StringProperty("")
    key    = StringProperty("")
    index  = None

    def refresh_view_attrs(self, rv, index, data):
        """Record the data index each time this recycled view is (re)bound."""
        self.index = index
        return super().refresh_view_attrs(rv, index, data)

    def on_long_touch(self, *args) -> None:
        """Long-pressing a file row opens its actions menu (folders ignored)."""
        if not self.is_dir and self.path:
            _open_actions_for(self)


class Mp3Tile(RecycleDataViewBehavior, ButtonBehavior, TouchBehavior, MDBoxLayout):
    """Album-art tile for the 타일 (tiles) grid view (a RecycleView viewclass)."""

    filename   = StringProperty("")
    artist     = StringProperty("")
    title      = StringProperty("")
    path       = StringProperty("")
    art_source = StringProperty("")
    index      = None

    def refresh_view_attrs(self, rv, index, data):
        """Record the index and lazily load this tile's album art when (re)bound."""
        self.index = index
        result = super().refresh_view_attrs(rv, index, data)
        app = MDApp.get_running_app()
        self.art_source = app._album_source(self.path) if app else ""
        return result

    def on_long_touch(self, *args) -> None:
        """Open the per-track actions menu on a long press."""
        _open_actions_for(self)


class CandidateRow(RecycleDataViewBehavior, TwoLineAvatarIconListItem):
    """A tappable online-search candidate row (a RecycleView viewclass)."""

    cand_title = StringProperty("")
    cand_sub   = StringProperty("")
    selected   = BooleanProperty(False)
    index      = None

    def refresh_view_attrs(self, rv, index, data):
        """Record the data index each time this recycled view is (re)bound."""
        self.index = index
        return super().refresh_view_attrs(rv, index, data)


# Register the row/tile viewclasses so RecycleView can resolve them by name.
Factory.register("Mp3RowDetails", cls=Mp3RowDetails)
Factory.register("Mp3RowList", cls=Mp3RowList)
Factory.register("Mp3TreeRow", cls=Mp3TreeRow)
Factory.register("Mp3Tile", cls=Mp3Tile)
Factory.register("CandidateRow", cls=CandidateRow)


class LyricsContent(MDBoxLayout):
    """Scrollable lyrics body for the 가사 dialog (laid out by its KV rule)."""


class TagEditContent(MDBoxLayout):
    """Editable tag-field form for the 자세히 dialog (laid out by its KV rule)."""


class SongInfoContent(MDBoxLayout):
    """Online-info dialog body: header, progress, status, candidate list."""


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
        self._db_path = os.path.join(self._storage_directory(), "mp3_archive.db")
        self._manager = Mp3Manager(self._db_path)
        self._selected: set[str] = set()   # selected file paths
        self._files: list = []             # current RecycleView data (list of dicts)

        # Playback state (재생 tab)
        self._sound = None             # current kivy Sound, or None
        self._paused_pos = 0.0         # remembered position for pause/resume (s)
        self._pos_event = None         # Clock event polling playback position
        self._suppress_next_play = False  # skip play_row right after a long-press

        # Folder picker (MDFileManager) state
        self._file_manager = None      # lazily-created MDFileManager
        self._fm_open = False          # whether the file manager is showing

        # Library / search state (목록 tab)
        self._search_keyword = ""      # current search text
        self._search_tags = False      # search all tags vs filename only
        self._last_dir = None          # last scanned directory (for full rescan)
        self._search_event = None      # debounce timer for live search

        # View mode (목록 tab): "details" (album art) / "list" / "tree"
        self._view_mode = "details"
        self._view_menu = None
        self._expanded: set = set()    # expanded folder keys (트리 view)
        self._art_cache: dict = {}     # path -> album-art file path ("" if none)
        self._art_dir = os.path.join(self._storage_directory(), "art_cache")
        try:
            os.makedirs(self._art_dir, exist_ok=True)
        except Exception:
            pass

        # Online-info (온라인 정보) dialog state
        self._song_content = None      # the open SongInfoContent, or None
        self._song_dialog = None       # the open MDDialog, or None
        self._song_candidates: list = []   # fetched candidate dicts
        self._song_sel = -1            # index of the chosen candidate (-1 = none)
        self._song_info_path = ""      # path of the track being looked up
        self._song_current: dict = {}  # current title/artist/album of that track
        self._song_source = SOURCE_ITUNES  # selected fetch source (default iTunes)
        self._source_menu = None       # the source-selector MDDropdownMenu
        self._batch_queue = None       # TagFetchQueue when in batch mode, else None
        self._batch_stem_tried = False  # auto-retried the filename stem this file

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

    # KivyMD 1.2.0 maps its font styles to several family names, not just
    # "Roboto": H1/H2 use "RobotoLight" and H6/Button use "RobotoMedium" (see
    # kivymd theming font_styles). Re-registering only "Roboto" left those
    # styles on the bundled Latin-only fonts, so headings and button labels
    # rendered Korean as tofu. Register the Korean font under every family.
    _KIVYMD_FONT_FAMILIES = (
        "Roboto", "RobotoThin", "RobotoLight", "RobotoMedium", "RobotoBlack",
    )

    def _register_fonts(self) -> None:
        """
        Register a Korean-capable font for every KivyMD font family.

        KivyMD's font styles reference several family names (Roboto,
        RobotoLight, RobotoMedium, …); pointing all of them at an Android
        system CJK font makes every style — body text, H6 headings and button
        labels — render Hangul instead of tofu boxes. No-op on platforms where
        no candidate font exists (e.g. desktop).
        """
        font_path = self._find_korean_font()
        if not font_path:
            return
        for name in self._KIVYMD_FONT_FAMILIES:
            LabelBase.register(
                name=name,
                fn_regular=font_path,
                fn_bold=font_path,
                fn_italic=font_path,
                fn_bolditalic=font_path,
            )

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
            # Navigate up one directory; MDFileManager.back() tears the picker
            # down (via exit_manager -> _close_file_manager) only at the root.
            self._file_manager.back()
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

    def force_rescan(self) -> None:
        """Re-scan the most recently scanned directory, re-reading every file."""
        if not self._last_dir:
            Snackbar(text="먼저 폴더를 선택해 스캔하세요.").open()
            return
        self._start_scan(self._last_dir, force=True)

    def _start_scan(self, directory: str, force: bool = False) -> None:
        """
        Launch a background thread to scan the given directory.

        Args:
            directory: Root path to scan for MP3 files.
            force:     When True, re-read every file and drop stale records.
        """
        self._last_dir = directory
        label = "전체 스캔 중" if force else "스캔 중"
        self._set_status(f"{label}: {os.path.basename(directory)}")
        self._set_progress_visible(True)
        self._set_progress(0)
        thread = threading.Thread(
            target=self._scan_worker,
            args=(directory, force),
            daemon=True,
        )
        thread.start()

    def _scan_worker(self, directory: str, force: bool = False) -> None:
        """
        Run Mp3Manager.scan() in a background thread and post UI updates.

        Args:
            directory: Directory path passed to Mp3Manager.scan().
            force:     Whether to force a full rescan.
        """
        def on_progress(current: int, total: int, path: str) -> None:
            """Schedule a progress bar update on the main thread."""
            pct = int(current / total * 100) if total else 0
            Clock.schedule_once(lambda dt: self._set_progress(pct))

        # Scan on a DEDICATED connection so this background thread never shares
        # the UI thread's sqlite connection — concurrent use of one connection
        # (e.g. live search during a scan) can raise ProgrammingError /
        # OperationalError. The UI re-reads the committed rows on its own
        # connection in _on_scan_done.
        scan_manager = Mp3Manager(self._db_path)
        try:
            # Re-scanning replaces the library: drop the previously scanned
            # entries so the list shows only the chosen folder's files.
            scan_manager.clear()
            result = scan_manager.scan(
                directory, progress_callback=on_progress, force=force
            )
        finally:
            scan_manager.close()
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
        """
        Repopulate the MP3 list, honouring the current search keyword.

        Assigns the RecycleView's data (a list of plain dicts) instead of
        creating a widget per song, so repopulating stays fast no matter how
        many songs match — only the on-screen rows are instantiated. Selection
        state is carried in the data so it survives recycling.
        """
        if self.root is None:
            return  # KV may fire on_text before build() returns and sets root

        if self._search_keyword:
            files = self._manager.search(
                self._search_keyword, filename_only=not self._search_tags
            )
        else:
            files = self._manager.list_files()

        self._files = [
            {
                "filename": f["filename"],
                "artist": f["artist"] or "-",
                "title": f["title"] or "-",
                "path": f["path"],
                "selected": f["path"] in self._selected,
            }
            for f in files
        ]
        if self._view_mode == "tiles":
            self.root.ids.mp3_grid.data = self._files
        elif self._view_mode == "tree":
            self.root.ids.mp3_list.data = build_tree_rows(
                self._files, self._last_dir or "", self._expanded
            )
        else:
            self.root.ids.mp3_list.data = self._files
        self.root.ids.count_label.text = self._count_label_text(
            len(files), self._search_keyword
        )

    # Live-search debounce delay (s). The Korean IME fires on_text for every
    # intermediate jamo while composing a syllable; rebuilding the whole list
    # on each one is slow and can wedge the UI, so coalesce rapid changes.
    _SEARCH_DEBOUNCE = 0.35

    def on_search_text(self, text: str) -> None:
        """
        Filter the list shortly after the search text stops changing.

        Debounced so Hangul IME composition (which fires on_text per jamo)
        rebuilds the list once, after typing pauses, instead of on every
        keystroke.

        Args:
            text: Current search-field text.
        """
        self._search_keyword = text.strip()
        if self._search_event is not None:
            self._search_event.cancel()
        self._search_event = Clock.schedule_once(
            lambda _dt: self._refresh_list(), self._SEARCH_DEBOUNCE
        )

    def on_search_tags(self, active: bool) -> None:
        """
        Toggle searching all tag fields vs the filename only.

        Args:
            active: True to search all tags; False for filename only.
        """
        self._search_tags = bool(active)
        if self._search_keyword:
            self._refresh_list()

    def clear_search(self) -> None:
        """Clear the search field, restoring the full list."""
        self.root.ids.search_field.text = ""

    @staticmethod
    def _count_label_text(n: int, keyword: str) -> str:
        """
        Build the song-count label text.

        Args:
            n:       Number of rows currently shown.
            keyword: Active search keyword ("" when not searching).

        Returns:
            "검색 결과: N곡" when searching, else "전체 N곡".
        """
        if keyword:
            return f"검색 결과: {n}곡"
        return f"전체 {n}곡"

    def toggle_select(self, row) -> None:
        """
        Toggle the selection state of a list row.

        Args:
            row: The Mp3Row widget that was tapped.
        """
        selected = row.path not in self._selected
        if selected:
            self._selected.add(row.path)
        else:
            self._selected.discard(row.path)
        row.selected = selected                      # instant feedback on this view
        if row.index is not None and 0 <= row.index < len(self._files):
            self._files[row.index]["selected"] = selected   # persist across recycling

    # ------------------------------------------------------------------
    # View mode (목록 / 자세히)
    # ------------------------------------------------------------------

    def open_view_menu(self) -> None:
        """Open the 보기 dropdown to choose the list view mode."""
        if self._view_menu is None:
            items = [
                {"text": "목록", "viewclass": "OneLineListItem",
                 "on_release": lambda: self._set_view_mode("list")},
                {"text": "자세히", "viewclass": "OneLineListItem",
                 "on_release": lambda: self._set_view_mode("details")},
                {"text": "트리", "viewclass": "OneLineListItem",
                 "on_release": lambda: self._set_view_mode("tree")},
                {"text": "타일", "viewclass": "OneLineListItem",
                 "on_release": lambda: self._set_view_mode("tiles")},
            ]
            self._view_menu = MDDropdownMenu(
                caller=self.root.ids.toolbar, items=items, width_mult=3,
            )
        self._view_menu.open()

    def _set_view_mode(self, mode: str) -> None:
        """Switch the list view mode and re-render."""
        if self._view_menu is not None:
            self._view_menu.dismiss()
        self._view_mode = mode
        self._apply_view_mode()
        self._refresh_list()

    def _apply_view_mode(self) -> None:
        """Show the list or tile RecycleView and set its viewclass for the mode."""
        rv = self.root.ids.mp3_list
        grid = self.root.ids.mp3_grid
        if self._view_mode == "tiles":
            # Show the album-art grid, collapse the list RecycleView.
            rv.size_hint_y = None
            rv.height = 0
            rv.opacity = 0
            grid.size_hint_y = 1
            grid.opacity = 1
            return
        # List/details/tree all use the (box-layout) list RecycleView.
        grid.size_hint_y = None
        grid.height = 0
        grid.opacity = 0
        rv.size_hint_y = 1
        rv.opacity = 1
        if self._view_mode == "list":
            rv.viewclass = "Mp3RowList"
            rv.layout_manager.default_size = (None, dp(48))
        elif self._view_mode == "tree":
            rv.viewclass = "Mp3TreeRow"
            rv.layout_manager.default_size = (None, dp(48))
        else:
            rv.viewclass = "Mp3RowDetails"
            rv.layout_manager.default_size = (None, dp(72))

    def _album_source(self, path: str) -> str:
        """
        Return a file path to the track's album art, caching each extraction.

        Embedded art bytes are written once to the per-app art cache and the
        path is reused; tracks without art (or on any failure) return "".

        Args:
            path: Absolute path to the audio file.

        Returns:
            A cached image file path, or "" when there is no art.
        """
        cached = self._art_cache.get(path)
        if cached is not None:
            return cached
        src = ""
        try:
            data = get_album_art(path)
            if data:
                ext = "png" if data[:4] == b"\x89PNG" else "jpg"
                fn = os.path.join(self._art_dir, "%x.%s" % (abs(hash(path)), ext))
                with open(fn, "wb") as fh:
                    fh.write(data)
                src = fn
        except Exception:
            src = ""
        self._art_cache[path] = src
        return src

    def tree_row_tapped(self, row) -> None:
        """Toggle a folder, or play a file, when a 트리 row is tapped."""
        if self._suppress_next_play:
            self._suppress_next_play = False
            return  # a long-press just opened the actions menu; don't also play
        if row.is_dir:
            self.toggle_tree_folder(row.key)
        elif row.path:
            self._play(row.path, os.path.basename(row.path), "")
            try:
                self.root.ids.bottom_nav.switch_tab("player")
            except Exception:
                pass

    def toggle_tree_folder(self, key: str) -> None:
        """Expand/collapse a tree folder and rebuild the visible tree rows."""
        if key in self._expanded:
            self._expanded.discard(key)
        else:
            self._expanded.add(key)
        self.root.ids.mp3_list.data = build_tree_rows(
            self._files, self._last_dir or "", self._expanded
        )

    # ------------------------------------------------------------------
    # Playback (재생 tab)
    # ------------------------------------------------------------------

    def play_row(self, row) -> None:
        """
        Play the track for a tapped list row and switch to the player tab.

        Tapping the row body plays; tapping the row's right icon selects it
        for deletion (see toggle_select).

        Args:
            row: The Mp3Row whose audio file should be played.
        """
        if self._suppress_next_play:
            self._suppress_next_play = False
            return  # a long-press just opened the actions menu; don't also play
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
        self.root.ids.pos_label.text = self._format_time(0)
        self.root.ids.dur_label.text = self._format_time(0)
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
        """Stop playback, unload the sound, and reset the player to idle."""
        self._stop_sound()
        self._paused_pos = 0.0
        self.root.ids.play_button.icon = "play"
        self.root.ids.position_bar.value = 0
        self.root.ids.pos_label.text = self._format_time(0)
        self.root.ids.dur_label.text = self._format_time(0)
        self.root.ids.now_playing.text = "재생 중인 곡이 없습니다"
        self.root.ids.now_playing_sub.text = ""

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
        count = len(self._selected)
        for path in list(self._selected):
            self._manager.delete(path)
        self._selected.clear()
        self._refresh_list()
        Snackbar(text=f"{count}개 항목이 삭제되었습니다.").open()

    # ------------------------------------------------------------------
    # Metadata dialogs (자세히 / 가사)
    # ------------------------------------------------------------------

    def open_actions(self, row) -> None:
        """
        Show the per-track actions menu for a long-pressed row.

        Args:
            row: The Mp3Row that was long-pressed.
        """
        self._actions_dialog = MDDialog(
            title=(getattr(row, "title", "") or getattr(row, "filename", "")
                   or os.path.basename(getattr(row, "path", ""))),
            text=getattr(row, "artist", ""),
            buttons=[
                MDFlatButton(text="자세히", on_release=lambda x: self._open_detail(row)),
                MDFlatButton(text="가사", on_release=lambda x: self._open_lyrics(row)),
                MDFlatButton(text="온라인", on_release=lambda x: self._open_song_info(row)),
                MDFlatButton(text="닫기", on_release=lambda x: self._actions_dialog.dismiss()),
            ],
        )
        self._actions_dialog.open()

    def _open_lyrics(self, row) -> None:
        """Show the embedded lyrics for a track in a scrollable dialog."""
        self._actions_dialog.dismiss()
        content = LyricsContent()
        content.ids.lyrics_label.text = get_lyrics(row.path) or "(가사 정보가 없습니다)"
        self._lyrics_dialog = MDDialog(
            title=(getattr(row, "title", "") or getattr(row, "filename", "")
                   or os.path.basename(getattr(row, "path", ""))),
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="닫기", on_release=lambda x: self._lyrics_dialog.dismiss()),
            ],
        )
        self._lyrics_dialog.open()

    def _open_detail(self, row) -> None:
        """Show an editable tag form for a track, prefilled from the database."""
        self._actions_dialog.dismiss()
        info = self._manager.get_by_path(row.path) or {}
        content = TagEditContent()
        # Show the embedded album art at the top when present; collapse the
        # image area to nothing when the track has no art.
        art = self._album_source(row.path)
        content.ids.art_image.source = art
        if art:
            content.ids.art_image.opacity = 1
            content.ids.art_image.height = dp(140)
        else:
            content.ids.art_image.opacity = 0
            content.ids.art_image.height = 0
        content.ids.f_title.text   = info.get("title")   or ""
        content.ids.f_artist.text  = info.get("artist")  or ""
        content.ids.f_album.text   = info.get("album")   or ""
        content.ids.f_genre.text   = info.get("genre")   or ""
        content.ids.f_year.text    = info.get("year")    or ""
        content.ids.f_comment.text = info.get("comment") or ""
        self._detail_content = content
        self._detail_path = row.path
        self._detail_dialog = MDDialog(
            title="자세히",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="저장", on_release=lambda x: self._save_detail()),
                MDFlatButton(text="닫기", on_release=lambda x: self._detail_dialog.dismiss()),
            ],
        )
        self._detail_dialog.open()

    def _save_detail(self) -> None:
        """Write the edited tag fields to the file and DB, then refresh the list."""
        c = self._detail_content
        form = {
            "title":   c.ids.f_title.text,
            "artist":  c.ids.f_artist.text,
            "album":   c.ids.f_album.text,
            "genre":   c.ids.f_genre.text,
            "year":    c.ids.f_year.text,
            "comment": c.ids.f_comment.text,
        }
        tags = to_easy_tags(form)
        if not tags:
            Snackbar(text="변경할 태그 내용이 없습니다.").open()
            self._detail_dialog.dismiss()
            return
        try:
            self._manager.update_tags(self._detail_path, tags)
            Snackbar(text="태그가 저장되었습니다.").open()
        except Exception:
            Snackbar(text="태그 저장에 실패했습니다.").open()
        self._detail_dialog.dismiss()
        self._refresh_list()

    # ------------------------------------------------------------------
    # Online metadata (온라인 정보)
    # ------------------------------------------------------------------

    def _open_song_info(self, row) -> None:
        """
        Open the online-info dialog for one track and start an online search.

        Shows the track's current tags read-only, then fetches ranked
        candidates from the selected source on a background thread. The user
        can change the source / search term, pick a candidate, and apply it to
        the file + DB.

        Args:
            row: The long-pressed row whose .path identifies the track.
        """
        self._actions_dialog.dismiss()
        info = self._manager.get_by_path(row.path) or {}
        self._batch_queue = None       # single-song mode
        self._song_info_path = row.path
        # Snapshot the fields that 태그 적용 can overwrite (title/artist/album),
        # so the detail panel can show a current → proposed diff per candidate.
        self._song_current = {
            "title":  info.get("title")  or "",
            "artist": info.get("artist") or "",
            "album":  info.get("album")  or "",
        }
        self._song_candidates = []
        self._song_sel = -1
        content = SongInfoContent()
        self._song_content = content
        content.ids.si_source_btn.text = self._source_label(self._song_source)
        filename = os.path.basename(row.path)
        cur_artist = info.get("artist") or "-"
        cur_title = info.get("title") or "-"
        content.ids.si_header.text = (
            f"{filename}\n현재: {cur_artist} — {cur_title}"
        )
        artist, title = build_song_query(info)
        content.ids.si_keyword.text = " ".join(p for p in (artist, title) if p)
        self._song_dialog = MDDialog(
            title="온라인 정보",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="태그 적용",
                             on_release=lambda x: self._apply_song_candidate()),
                MDFlatButton(text="닫기",
                             on_release=lambda x: self._close_song_dialog()),
            ],
        )
        self._song_dialog.open()
        self._start_song_search(artist, title)

    def _close_song_dialog(self) -> None:
        """Dismiss the online-info dialog, clear its state, and refresh if needed."""
        if self._source_menu is not None:
            self._source_menu.dismiss()
        if self._song_dialog is not None:
            self._song_dialog.dismiss()
        self._song_content = None
        if self._batch_queue is not None:
            # Batch mode may have applied tags to several files; show them.
            self._batch_queue = None
            self._refresh_list()

    @staticmethod
    def _source_label(source: str) -> str:
        """
        Return the human-readable label for a fetch-source identifier.

        Args:
            source: A SOURCE_* identifier (e.g. "itunes").

        Returns:
            The matching UI label (e.g. "iTunes"); falls back to the
            identifier itself if it is unknown.
        """
        for label, ident in SOURCE_LABELS:
            if ident == source:
                return label
        return source

    def open_source_menu(self) -> None:
        """Open the dropdown that selects which online source(s) to search."""
        if self._song_content is None:
            return
        caller = self._song_content.ids.si_source_btn
        items = [
            {"text": label, "viewclass": "OneLineListItem",
             "on_release": (lambda s=ident, l=label: self._set_song_source(s, l))}
            for label, ident in SOURCE_LABELS
        ]
        self._source_menu = MDDropdownMenu(caller=caller, items=items, width_mult=3)
        self._source_menu.open()

    def _set_song_source(self, source: str, label: str) -> None:
        """
        Switch the active fetch source and re-run the current search.

        Args:
            source: The chosen SOURCE_* identifier.
            label:  Its display label, shown on the source button.
        """
        if self._source_menu is not None:
            self._source_menu.dismiss()
        self._song_source = source
        if self._song_content is not None:
            self._song_content.ids.si_source_btn.text = label
        self.on_song_search()

    def on_song_search(self) -> None:
        """
        Run an online search using the keyword field, or the auto terms.

        When the keyword field holds text it is searched as a free title term;
        otherwise the track's auto-detected artist/title (or the batch queue's
        current terms) are used.
        """
        c = self._song_content
        if c is None:
            return
        keyword = c.ids.si_keyword.text.strip()
        if keyword:
            self._start_song_search(None, keyword)
        else:
            artist, title = self._song_auto_terms()
            self._start_song_search(artist, title)

    def _song_auto_terms(self) -> tuple:
        """Return the (artist, title) auto-search terms for the current track."""
        if self._batch_queue is not None and not self._batch_queue.is_done():
            return self._batch_queue.query_terms()
        info = self._manager.get_by_path(self._song_info_path) or {}
        return build_song_query(info)

    def _start_song_search(self, artist: str | None, title: str | None) -> None:
        """
        Kick off an online search on a daemon thread for the current source.

        Args:
            artist: Cleaned artist query term, or None.
            title:  Cleaned title query term, or None.
        """
        c = self._song_content
        if c is None:
            return
        c.ids.si_status.text = "검색 중..."
        c.ids.si_progress.opacity = 1
        c.ids.si_results.data = []
        thread = threading.Thread(
            target=self._song_search_worker,
            args=(artist, title, self._song_source),
            daemon=True,
        )
        thread.start()

    def _song_search_worker(
        self, artist: str | None, title: str | None, source: str
    ) -> None:
        """
        Run the network search off the UI thread and post results back.

        Args:
            artist: Artist query term (may be None).
            title:  Title query term (may be None).
            source: The SOURCE_* identifier to query.
        """
        try:
            candidates = fetch_candidates(artist, title, source)
        except Exception:
            candidates = []
        Clock.schedule_once(
            lambda dt: self._on_song_results(candidates, source)
        )

    @mainthread
    def _on_song_results(self, candidates: list, source: str) -> None:
        """
        Display fetched candidates in the dialog (runs on the UI thread).

        In batch mode a no-result search auto-retries once with the current
        file's filename stem before reporting "no match", since a tag-based
        query often fails where the bare filename succeeds.

        Args:
            candidates: Merged candidate dicts (possibly empty).
            source:     The SOURCE_* identifier that produced them.
        """
        if self._song_content is None:
            return  # dialog was closed before the search returned
        c = self._song_content

        # Batch auto-retry: if nothing matched, try the filename stem once.
        if (not candidates and self._batch_queue is not None
                and not self._batch_stem_tried):
            stem = self._batch_queue.auto_retry_keyword()
            if stem and stem != c.ids.si_keyword.text.strip():
                self._batch_stem_tried = True
                c.ids.si_keyword.text = stem
                c.ids.si_status.text = f"결과 없음 — 파일명으로 재검색: {stem}"
                self._start_song_search(None, stem)
                return

        c.ids.si_progress.opacity = 0
        self._song_candidates = candidates
        self._song_sel = 0 if candidates else -1
        if candidates:
            c.ids.si_status.text = f"{len(candidates)}개 후보 — 선택 후 태그 적용"
        else:
            err = self._fetch_error(source)
            if err:
                c.ids.si_status.text = f"검색 실패: {err}"
            else:
                c.ids.si_status.text = "검색 결과 없음 (일치하는 곡이 없습니다)"
        self._render_song_candidates()

    @staticmethod
    def _fetch_error(source: str) -> str:
        """
        Return the last network error recorded by the queried source(s).

        Args:
            source: The SOURCE_* identifier that was searched.

        Returns:
            The fetcher's last_error string, or "" when the empty result was a
            genuine no-match rather than a network/TLS failure.
        """
        if source in (SOURCE_ITUNES, SOURCE_BOTH) and itunes_fetcher.last_error:
            return itunes_fetcher.last_error
        if source in (SOURCE_MB, SOURCE_BOTH) and mb_fetcher.last_error:
            return mb_fetcher.last_error
        return ""

    def _render_song_candidates(self) -> None:
        """Rebuild the candidate RecycleView data and refresh the detail panel."""
        if self._song_content is None:
            return
        data = []
        for i, cand in enumerate(self._song_candidates):
            parts = [
                cand.get("source", ""),
                cand.get("artist", ""),
                cand.get("album", ""),
                cand.get("year", ""),
                cand.get("length", ""),
                cand.get("disambiguation", ""),
            ]
            sub = " · ".join(p for p in parts if p)
            score = cand.get("score", 0)
            data.append({
                "cand_title": cand.get("title", "") or "(제목 없음)",
                "cand_sub": f"{sub}   ★{score}" if sub else f"★{score}",
                "selected": (i == self._song_sel),
            })
        self._song_content.ids.si_results.data = data
        self._song_content.ids.si_detail.text = self._song_detail_text(
            self._selected_candidate(), self._song_current
        )

    def _selected_candidate(self) -> dict | None:
        """Return the currently-selected candidate dict, or None if none picked."""
        if 0 <= self._song_sel < len(self._song_candidates):
            return self._song_candidates[self._song_sel]
        return None

    @staticmethod
    def _song_detail_text(cand: dict | None, current: dict | None = None) -> str:
        """
        Format the detail block shown below the candidate list.

        Leads with a field-by-field "what 태그 적용 will change" diff for the
        three writable tags (title/artist/album), comparing the track's
        current value against the selected candidate's value, so the user can
        see exactly what each candidate would overwrite before choosing one.
        Below the diff it lists the recording's duration, qualifier, and every
        alternate release, which helps tell two takes of the same song apart.

        Args:
            cand:    The selected candidate dict (from mb_fetcher.search), or
                     None when no candidate is selected.
            current: The track's current {title, artist, album} values. When
                     None, every candidate field is treated as a change.

        Returns:
            A newline-joined detail block. Empty string when ``cand`` is None.
        """
        if not cand:
            return ""
        current = current or {}
        lines: list[str] = ["적용 시 변경되는 태그:"]

        changed = False
        for label, key in (("제목", "title"), ("아티스트", "artist"),
                           ("앨범", "album")):
            new = (cand.get(key) or "").strip()
            cur = (current.get(key) or "").strip()
            if not new:
                # update_file_tags skips empty fields, so the tag is untouched.
                lines.append(f"  · {label}: {cur or '-'} (유지)")
            elif new == cur:
                lines.append(f"  · {label}: {cur} (동일)")
            else:
                changed = True
                lines.append(f"  ✔ {label}: {cur or '-'} → {new}")
        if not changed:
            lines.append("  (바뀌는 태그가 없습니다)")

        year = cand.get("year", "") or "-"
        length = cand.get("length", "") or "-"
        disamb = cand.get("disambiguation", "") or "-"
        lines.append("")
        lines.append(f"발매: {year}    길이: {length}    비고: {disamb}")
        releases = cand.get("releases") or []
        alternates = [
            r for r in releases
            if (r.get("title") or "") != (cand.get("album") or "")
        ]
        if alternates:
            lines.append("다른 앨범:")
            for rel in alternates[:6]:
                title = rel.get("title", "") or "-"
                year = rel.get("year", "") or "-"
                rtype = rel.get("type", "")
                tail = f"{year}, {rtype}" if rtype else year
                lines.append(f"  · {title} ({tail})")
            if len(alternates) > 6:
                lines.append(f"  · 그 외 {len(alternates) - 6}개")
        return "\n".join(lines)

    def select_candidate(self, row) -> None:
        """
        Mark the tapped candidate as the chosen one and re-render the list.

        Args:
            row: The CandidateRow that was tapped (its .index is the position).
        """
        if row.index is None:
            return
        self._song_sel = row.index
        self._render_song_candidates()

    def _apply_song_candidate(self) -> None:
        """
        Write the selected candidate's tags to the file + DB.

        In single-song mode this closes the dialog and refreshes the list. In
        batch mode it records the application and advances to the next queued
        file, keeping the dialog open until the queue is exhausted.
        """
        if not self._song_candidates or self._song_sel < 0:
            Snackbar(text="선택된 후보가 없습니다.").open()
            return
        cand = self._song_candidates[self._song_sel]
        try:
            self._manager.update_file_tags(
                self._song_info_path,
                cand.get("title") or None,
                cand.get("artist") or None,
                cand.get("album") or None,
            )
        except Exception:
            Snackbar(text="태그 적용에 실패했습니다.").open()
            return

        if self._batch_queue is not None:
            self._batch_queue.mark_applied()
            Snackbar(text="태그가 적용되었습니다.").open()
            self._load_batch_current()
            return

        Snackbar(text="태그가 적용되었습니다.").open()
        if self._song_dialog is not None:
            self._song_dialog.dismiss()
        self._song_content = None
        self._refresh_list()

    # ------------------------------------------------------------------
    # Batch tag auto-completion (태그 자동 완성)
    # ------------------------------------------------------------------

    def start_batch_tag_fetch(self) -> None:
        """
        Open the batch dialog that completes tags for files missing title/artist.

        Builds a TagFetchQueue from the current library (only files missing a
        core tag), then steps through them one at a time, reusing the online
        search UI with 적용 / 건너뛰기 controls and an (M / N) counter.
        """
        queue = TagFetchQueue(self._manager.list_files())
        if queue.is_done():
            Snackbar(text="태그가 없는 파일이 없습니다.").open()
            return
        self._batch_queue = queue
        self._song_candidates = []
        self._song_sel = -1
        content = SongInfoContent()
        self._song_content = content
        content.ids.si_source_btn.text = self._source_label(self._song_source)
        self._song_dialog = MDDialog(
            title="태그 자동 완성",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="적용",
                             on_release=lambda x: self._apply_song_candidate()),
                MDFlatButton(text="건너뛰기",
                             on_release=lambda x: self._batch_skip()),
                MDFlatButton(text="닫기",
                             on_release=lambda x: self._close_song_dialog()),
            ],
        )
        self._song_dialog.open()
        self._load_batch_current()

    def _load_batch_current(self) -> None:
        """Show the current queued file and start its search, or finish up."""
        queue = self._batch_queue
        c = self._song_content
        if queue is None or c is None:
            return
        if queue.is_done():
            c.ids.si_header.text = (
                f"완료: {queue.applied_count()}개 적용 / {queue.total()}개 처리"
            )
            c.ids.si_status.text = "모든 파일을 처리했습니다."
            c.ids.si_progress.opacity = 0
            c.ids.si_results.data = []
            c.ids.si_detail.text = ""
            c.ids.si_keyword.text = ""
            self._song_candidates = []
            self._song_sel = -1
            return
        f = queue.current()
        self._song_info_path = f["path"]
        self._song_current = {
            "title":  f.get("title")  or "",
            "artist": f.get("artist") or "",
            "album":  f.get("album")  or "",
        }
        self._batch_stem_tried = False
        filename = f.get("filename") or os.path.basename(f["path"])
        cur_artist = f.get("artist") or "-"
        cur_title = f.get("title") or "-"
        c.ids.si_header.text = (
            f"{queue.counter_text()} {filename}\n현재: {cur_artist} — {cur_title}"
        )
        artist, title = queue.query_terms()
        c.ids.si_keyword.text = " ".join(p for p in (artist, title) if p)
        self._start_song_search(artist, title)

    def _batch_skip(self) -> None:
        """Skip the current queued file without applying any tags."""
        if self._batch_queue is not None:
            self._batch_queue.advance()
            self._load_batch_current()

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
