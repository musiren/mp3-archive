[app]

# Application identity
title = MP3 Archive
package.name = mp3archive
package.domain = org.musiren

# Source: buildozer looks for main.py inside source.dir
source.dir = src
source.include_exts = py,png,jpg,kv,atlas

# Launcher icon: reuse the desktop app icon (square 1024x1024 PNG).
# Path is resolved relative to this spec file's directory.
icon.filename = %(source.dir)s/../assets/icon.png

version = 1.0.0

# Built against CPython 3.11.5 (pinned via p4a.branch below). kivy 2.3.0
# compiles cleanly there with Cython 0.29.x; kivymd 1.2.0 needs kivy>=2.1.0.
requirements = python3,kivy==2.3.0,kivymd==1.2.0,plyer,mutagen

orientation = portrait
fullscreen = 0

# Android-specific
android.presplash_color = #FFFFFF

# READ_EXTERNAL_STORAGE / WRITE_EXTERNAL_STORAGE cover API < 33;
# READ_MEDIA_AUDIO covers API 33+ (Android 13). MANAGE_EXTERNAL_STORAGE
# ("All files access") is required to browse and scan arbitrary directories
# under scoped storage (Android 11+); it is granted via a settings page, not
# a runtime prompt (see Mp3ArchiveApp._request_all_files_access).
#
# INTERNET is required for online metadata lookups (MusicBrainz / iTunes tag
# fetch). It is a normal, install-time permission with no runtime prompt.
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_AUDIO,MANAGE_EXTERNAL_STORAGE,INTERNET

android.api = 33
android.minapi = 21
android.ndk = 25b
android.build_tools_version = 33.0.2

# Build for both 64-bit and 32-bit ARM devices.
android.archs = arm64-v8a, armeabi-v7a

android.allow_backup = True

# Pin python-for-android to the v2024.01.21 release. Its python3 recipe
# builds CPython 3.11.5; p4a master builds CPython 3.14, against which
# kivy 2.3.0 fails to compile (it calls private C-API removed/changed in
# 3.14, e.g. _PyList_Extend and the 6-arg _PyLong_AsByteArray). This
# release supports NDK r25 only, hence android.ndk = 25b above.
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
