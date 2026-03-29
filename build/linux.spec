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

import sys
from pathlib import Path

block_cipher = None

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

pyqt6_datas = collect_data_files("PyQt6")
mutagen_datas = collect_data_files("mutagen")

a = Analysis(
    scripts=["src/main_window.py"],
    pathex=["src"],
    binaries=collect_dynamic_libs("PyQt6"),
    datas=pyqt6_datas + mutagen_datas + [("src/main_window.ui", ".")],
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
        "mp3_manager",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "email",
        "html",
        "http",
        "urllib",
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
    strip=True,            # Strip debug symbols to reduce binary size
    upx=True,              # Compress with UPX if available
    upx_exclude=[],
    runtime_tmpdir=None,
    icon=None,             # Replace with "assets/icon.png" if you have one
)
