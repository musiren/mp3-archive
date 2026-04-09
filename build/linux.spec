# build/linux.spec
# PyInstaller spec file for building mp3-archive (Linux, standalone).
#
# Build command (run from project root):
#   pyinstaller build/linux.spec
#
# Requirements:
#   pip install pyinstaller pyqt6 mutagen
#
# Output:
#   dist/mp3-archive  (single self-contained executable)

import os
import sys
from pathlib import Path

block_cipher = None

# SPECPATH is the directory containing this spec file (i.e. build/).
# ROOT is the project root (one level up).
ROOT = os.path.dirname(SPECPATH)

from PyInstaller.utils.hooks import (
    collect_data_files, collect_dynamic_libs, collect_submodules
)

pyqt6_datas   = collect_data_files("PyQt6")
mutagen_datas = collect_data_files("mutagen")

a = Analysis(
    scripts=[os.path.join(ROOT, "src", "main_window.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=collect_dynamic_libs("PyQt6"),
    datas=pyqt6_datas + mutagen_datas + [
        (os.path.join(ROOT, "src", "main_window.ui"), "."),
        (os.path.join(ROOT, "assets", "icon.png"), "assets"),
    ],
    hiddenimports=[
        # PyQt6
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtMultimedia",
        "PyQt6.sip",
        # mutagen — collect all submodules so every format codec is included
        *collect_submodules("mutagen"),
        # musicbrainzngs — collect all submodules
        *collect_submodules("musicbrainzngs"),
        # Standard library modules that PyInstaller's static analysis often misses
        "sqlite3",
        "ipaddress",
        "ssl",
        "http.client",
        "urllib.parse",
        "urllib.request",
        "urllib.error",
        "encodings.utf_8",
        "encodings.ascii",
        "encodings.latin_1",
        # Application modules
        "mp3_manager",
        "tag_fetcher",
        "tag_fetch_dialog",
        "itunes_fetcher",
        "song_info_dialog",
        "tag_detail_dialog",
        "lyrics_dialog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "xmlrpc",
    ],
    cipher=block_cipher,
    noarchive=True,   # store .pyc files directly on disk instead of in a PKG archive
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onedir mode: exclude_binaries=True keeps the exe small; COLLECT bundles
# all libraries alongside it in dist/mp3-archive/. No /tmp extraction needed.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,

    name="mp3-archive",

    # Linux does not use a windowed subsystem flag; the GUI hides the terminal
    console=False,

    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    icon=os.path.join(ROOT, "assets", "icon.png"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="mp3-archive",
)
