# build/windows.spec
# PyInstaller spec file for building mp3-archive.exe (Windows, standalone).
#
# Build command (run from project root):
#   pyinstaller build/windows.spec
#
# Requirements:
#   pip install pyinstaller pyqt6 mutagen
#
# Output:
#   dist/mp3-archive.exe  (single self-contained executable)

import sys
from pathlib import Path

block_cipher = None

# ---------------------------------------------------------------------------
# Collect all data files required by PyQt6 (translations, plugins, etc.)
# ---------------------------------------------------------------------------
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

pyqt6_datas = collect_data_files("PyQt6")
mutagen_datas = collect_data_files("mutagen")

a = Analysis(
    # Entry point
    scripts=["src/main_window.py"],

    # Search paths so 'from mp3_manager import ...' resolves correctly
    pathex=["src"],

    # Shared libraries to bundle (PyQt6 platform plugins, etc.)
    binaries=collect_dynamic_libs("PyQt6"),

    # Data files (Qt translations, Qt plugins)
    datas=pyqt6_datas + mutagen_datas + [("src/main_window.ui", ".")],

    # Python-level hidden imports that PyInstaller may miss
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

    # Modules to exclude to reduce binary size
    excludes=[
        "tkinter",
        "unittest",
        "xmlrpc",
    ],

    win_no_prefer_redirects=False,
    win_private_assemblies=False,
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

    # Single-file executable (extracts to %TEMP% at runtime)
    name="mp3-archive",
    onefile=True,

    # No console window (GUI application)
    console=False,

    # Windows-specific metadata
    version_file=None,
    uac_admin=False,

    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,          # Compress with UPX if available (reduces size)
    upx_exclude=[],
    runtime_tmpdir=None,
    icon=None,         # Replace with "assets/icon.ico" if you have one
)
