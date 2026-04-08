#!/usr/bin/env bash
# build/package_deb.sh
#
# Build a .deb package for mp3-archive.
#
# Usage (run from project root):
#   bash build/package_deb.sh [version]
#
# Examples:
#   bash build/package_deb.sh          # version read from NEWS (e.g. 20260407)
#   bash build/package_deb.sh 1.2.0    # override version
#
# Requirements:
#   pip install pyinstaller pyqt6 mutagen
#   dpkg-deb (included in dpkg, standard on Debian/Ubuntu)
#
# Output:
#   dist/mp3-archive_<version>_amd64.deb

set -euo pipefail

SCRIPT_DIR_TMP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_TMP="$(dirname "$SCRIPT_DIR_TMP")"

# Read version from NEWS if not supplied as an argument.
# NEWS lines look like: "v20260407 (2026-04-07)" → extract "20260407"
if [ -n "${1:-}" ]; then
    VERSION="$1"
else
    VERSION=$(grep -m1 '^v[0-9]' "$ROOT_TMP/NEWS" | sed 's/^v//' | awk '{print $1}')
    if [ -z "$VERSION" ]; then
        echo "ERROR: could not parse version from NEWS" >&2
        exit 1
    fi
    echo "==> Version from NEWS: $VERSION"
fi
SCRIPT_DIR="$SCRIPT_DIR_TMP"
ROOT="$ROOT_TMP"
STAGING="$ROOT/build/_deb_staging"
DEB_OUT="$ROOT/dist/mp3-archive_${VERSION}_amd64.deb"

echo "==> Building EXE with PyInstaller..."
cd "$ROOT"
pyinstaller build/linux.spec

echo "==> Setting up staging directory..."
rm -rf "$STAGING"

# /usr/lib/mp3-archive/   — main binary
install -Dm755 "$ROOT/dist/mp3-archive" \
               "$STAGING/usr/lib/mp3-archive/mp3-archive"

# /usr/bin/mp3-archive    — symlink so users can run it from PATH
install -d "$STAGING/usr/bin"
ln -sf /usr/lib/mp3-archive/mp3-archive \
       "$STAGING/usr/bin/mp3-archive"

# /usr/share/applications/ — .desktop entry for the app launcher
install -Dm644 "$SCRIPT_DIR/deb/mp3-archive.desktop" \
               "$STAGING/usr/share/applications/mp3-archive.desktop"

# /usr/share/pixmaps/     — app icon (PNG)
install -Dm644 "$ROOT/assets/icon.png" \
               "$STAGING/usr/share/pixmaps/mp3-archive.png"

# DEBIAN/control
install -d "$STAGING/DEBIAN"
sed "s/^Version:.*/Version: $VERSION/" \
    "$SCRIPT_DIR/deb/control" > "$STAGING/DEBIAN/control"

# DEBIAN/postinst — refresh desktop/icon caches after install
cat > "$STAGING/DEBIAN/postinst" << 'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache /usr/share/pixmaps 2>/dev/null || true
fi
EOF
chmod 755 "$STAGING/DEBIAN/postinst"

# DEBIAN/prerm — nothing to do before removal
cat > "$STAGING/DEBIAN/prerm" << 'EOF'
#!/bin/sh
set -e
EOF
chmod 755 "$STAGING/DEBIAN/prerm"

echo "==> Building .deb..."
mkdir -p "$ROOT/dist"
dpkg-deb --build --root-owner-group "$STAGING" "$DEB_OUT"

echo ""
echo "Done: $DEB_OUT"
echo ""
dpkg-deb --info "$DEB_OUT"
