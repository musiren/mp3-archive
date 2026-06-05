[app]

# Application identity
title = MP3 Archive
package.name = mp3archive
package.domain = org.musiren

# Source: buildozer looks for main.py inside source.dir
source.dir = src
source.include_exts = py,png,jpg,kv,atlas

version = 1.0.0

# Kivy 2.3.0+ uses Cython 3.x which does not depend on the `cgi` module
# (removed in Python 3.13+). KivyMD 1.2.0 requires kivy>=2.1.0 so 2.3.0 is fine.
requirements = python3,kivy==2.3.0,kivymd==1.2.0,plyer,mutagen

orientation = portrait
fullscreen = 0

# Android-specific
android.presplash_color = #FFFFFF

# READ_EXTERNAL_STORAGE / WRITE_EXTERNAL_STORAGE cover API < 33;
# READ_MEDIA_AUDIO covers API 33+ (Android 13).
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_AUDIO

android.api = 33
android.minapi = 21
android.ndk = 28c
android.build_tools_version = 33.0.2

# Build for both 64-bit and 32-bit ARM devices.
android.archs = arm64-v8a, armeabi-v7a

android.allow_backup = True

[buildozer]
log_level = 1
warn_on_root = 1
