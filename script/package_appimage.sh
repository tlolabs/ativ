#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="${1:?architecture}"; STAGE="${2:?package root}"; VERSION="${3:?version}"
LABEL=x64
case "$ARCH" in
 x86_64) DEPLOY_HASH=36a2d7e274d12e1050d0e9ecfe11d339ed54720b2bec464c286d53f8b07f5c62; IMAGE_HASH=a6d71e2b6cd66f8e8d16c37ad164658985e0cf5fcaa950c90a482890cb9d13e0 ;;
 aarch64) LABEL=arm64; DEPLOY_HASH=556ab80baa98e600aa80f0dcedfb70bca0e1ce7e9f147fb345be3fcc3e91b2b1; IMAGE_HASH=1b00524ba8c6b678dc15ef88a5c25ec24def36cdfc7e3abb32ddcd068e8007fe ;;
 *) exit 2 ;;
esac
TOOLS="$ROOT_DIR/build/appimage-tools-$ARCH"; APPDIR="$ROOT_DIR/build/ATIV-$ARCH.AppDir"
mkdir -p "$TOOLS"
fetch() { curl --fail --location --retry 3 --proto '=https' --proto-redir '=https' "$1" -o "$2"; printf '%s  %s\n' "$3" "$2" | sha256sum --check; chmod +x "$2"; }
fetch "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-$ARCH.AppImage" "$TOOLS/linuxdeploy" "$DEPLOY_HASH"
fetch "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage" "$TOOLS/appimagetool" "$IMAGE_HASH"
curl --fail --location --proto '=https' 'https://raw.githubusercontent.com/linuxdeploy/linuxdeploy-plugin-gtk/7a3fbc31a9e5075073ff8790f26effbac5f84453/linuxdeploy-plugin-gtk.sh' -o "$TOOLS/linuxdeploy-plugin-gtk.sh"
chmod +x "$TOOLS/linuxdeploy-plugin-gtk.sh"
rm -rf "$APPDIR"; mkdir -p "$APPDIR"; cp -a "$STAGE/usr" "$APPDIR/"
python3 "$ROOT_DIR/script/configure_distribution.py" "$APPDIR/usr/lib/ativ" "linux-$LABEL-appimage"
export APPIMAGE_EXTRACT_AND_RUN=1 DEPLOY_GTK_VERSION=4
export PATH="$TOOLS:$PATH"
DESKTOP="$(find "$APPDIR/usr/share/applications" -name '*.desktop' -print -quit)"
linuxdeploy --appdir "$APPDIR" --executable "$APPDIR/usr/bin/ativ" --desktop-file "$DESKTOP" --icon-file "$APPDIR/usr/share/icons/hicolor/256x256/apps/$(basename "$DESKTOP" .desktop).png" --plugin gtk
# linuxdeploy-generated AppRun supplies the relocatable runtime environment.
ARCH="$ARCH" "$TOOLS/appimagetool" "$APPDIR" "$ROOT_DIR/packages/ATIV-$VERSION-linux-$LABEL.AppImage"
python3 "$ROOT_DIR/script/validate_package.py" "$APPDIR" "linux-$LABEL-appimage"
