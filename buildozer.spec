[app]

# Application identity
title = MP3 Archive
package.name = mp3archive
package.domain = org.musiren

# Source: buildozer looks for main.py inside source.dir
source.dir = src
source.include_exts = py,png,jpg,kv,atlas

version = 1.0.0

# Python-for-android requirements.
# KivyMD 1.2.0 requires Kivy 2.2.1.
requirements = python3,kivy==2.2.1,kivymd==1.2.0,plyer,mutagen

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
log_level = 2
warn_on_root = 1
