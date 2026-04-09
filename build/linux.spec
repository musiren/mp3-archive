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

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

pyqt6_datas = collect_data_files("PyQt6")
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
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.sip",
        "mutagen",
        "mutagen.mp3",
        "mutagen.id3",
        "sqlite3",
        "musicbrainzngs",
        "tag_fetcher",
        "tag_fetch_dialog",
        "itunes_fetcher",
        "song_info_dialog",
        "tag_detail_dialog",
        "mp3_manager",
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
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,

    name="mp3-archive",
    onefile=True,

    # Linux does not use a windowed subsystem flag; the GUI hides the terminal
    console=False,

    debug=False,
    bootloader_ignore_signals=False,
    strip=False,           # Do NOT strip: stripping can corrupt PyInstaller's embedded archive
    upx=True,              # Compress with UPX if available
    upx_exclude=[],
    runtime_tmpdir=None,
    icon=os.path.join(ROOT, "assets", "icon.png"),
)
