# build/android.spec
# Buildozer spec file for building mp3-archive APK (Android).
#
# NOTE: PyQt6 is not supported on Android.
#       The UI layer (src/main_window.py) must be reimplemented
#       using Kivy or KivyMD before building for Android.
#       The backend library (src/mp3_manager.py) can be reused as-is.
#
# Requirements:
#   pip install buildozer cython
#   sudo apt install -y git zip unzip openjdk-17-jdk python3-pip
#   (first build will download Android SDK/NDK automatically)
#
# Build command:
#   buildozer -v android debug          # debug APK
#   buildozer -v android release        # release APK (requires keystore)
#
# Output:
#   bin/mp3-archive-<version>-arm64-v8a-debug.apk

[app]

# Application metadata
title           = MP3 Archive
package.name    = mp3archive
package.domain  = org.mp3archive
version         = 1.0.0

# Entry point
source.dir      = src
source.include_exts = py,png,jpg,kv,atlas,db
main            = main_window_android.py

# Python version
osx.python_version = 3
android.archs   = arm64-v8a, armeabi-v7a

# Dependencies
requirements = python3,kivy,kivymd,mutagen,sqlite3

# Orientation
orientation = portrait

# Android permissions
android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE

# Android API levels
android.minapi  = 26
android.api     = 33
android.ndk     = 25b
android.sdk     = 33

# Fullscreen
fullscreen = 0

# Android build tools
android.accept_sdk_license = True

[buildozer]

# Build directory
build_dir = .buildozer

# Logging
log_level = 2
