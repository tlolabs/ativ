#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="${1:-$(uname -m)}"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "${ROOT_DIR}/Cargo.toml" | head -n 1)"

VERSION="${ATIV_VERSION:-$VERSION}"
LABEL=x64
APP_ID=com.tlolabs.ativ
PACKAGE_NAME=ativ
if [[ "${ATIV_CHANNEL:-stable}" == development ]]; then APP_ID=com.tlolabs.ativ.development; PACKAGE_NAME=ativ-development; fi
case "${ARCH}" in
  x86_64) DEB_ARCH="amd64" ;;
  aarch64|arm64) ARCH="aarch64"; DEB_ARCH="arm64"; LABEL=arm64 ;;
  *) echo "unsupported Linux architecture: ${ARCH}" >&2; exit 2 ;;
esac
[[ "$(uname -m)" == "${ARCH}" || ( "$(uname -m)" == "arm64" && "${ARCH}" == "aarch64" ) ]] || { echo "Run on a native ${ARCH} Linux runner." >&2; exit 2; }
RUNTIME_TARGET="linux-$ARCH"
RUNTIME="$(python3 "$ROOT_DIR/script/ffmpeg_runtime.py" provision "$RUNTIME_TARGET")"

BUILD_DIR="${ROOT_DIR}/build/linux-${ARCH}"
PACKAGE_ROOT="${ROOT_DIR}/build/package-linux-${ARCH}"
PACKAGES="${ROOT_DIR}/packages"
rm -rf "${BUILD_DIR}" "${PACKAGE_ROOT}"
mkdir -p "${PACKAGE_ROOT}/DEBIAN" "${PACKAGE_ROOT}/usr/lib/ativ" "${PACKAGE_ROOT}/usr/share/doc/ativ" "${PACKAGES}"

cargo build --manifest-path "${ROOT_DIR}/Cargo.toml" --release --locked -p ativ-engine -p ativ-update
meson setup "${BUILD_DIR}" "${ROOT_DIR}/platform/linux" --prefix=/usr -Dengine_path=/usr/lib/$PACKAGE_NAME/ativ-engine -Dapp_id=$APP_ID
meson compile -C "${BUILD_DIR}"
DESTDIR="${PACKAGE_ROOT}" meson install -C "${BUILD_DIR}"
cp "${ROOT_DIR}/target/release/ativ-engine" "${PACKAGE_ROOT}/usr/lib/ativ/ativ-engine"
cp "${ROOT_DIR}/target/release/ativ-update" "${PACKAGE_ROOT}/usr/lib/ativ/ativ-update"
python3 "$ROOT_DIR/script/configure_distribution.py" "$PACKAGE_ROOT/usr/lib/ativ" "linux-$LABEL-deb"
python3 "$ROOT_DIR/script/ffmpeg_runtime.py" stage "$RUNTIME_TARGET" --runtime "$RUNTIME" --binary "$PACKAGE_ROOT/usr/lib/ativ"
python3 "$ROOT_DIR/script/ffmpeg_runtime.py" finish "$RUNTIME_TARGET" --binary "$PACKAGE_ROOT/usr/lib/ativ"
cp "${ROOT_DIR}/LICENSE" "${PACKAGE_ROOT}/usr/share/doc/ativ/LICENSE"
cp "${ROOT_DIR}/THIRD_PARTY_NOTICES.md" "${PACKAGE_ROOT}/usr/share/doc/ativ/THIRD_PARTY_NOTICES.md"
python3 "$ROOT_DIR/script/collect_licenses.py" "$PACKAGE_ROOT/usr/share/doc/ativ/licenses"
chmod 0755 "${PACKAGE_ROOT}/usr/bin/ativ" "${PACKAGE_ROOT}/usr/lib/ativ/ativ-engine" "${PACKAGE_ROOT}/usr/lib/ativ/ffmpeg" "${PACKAGE_ROOT}/usr/lib/ativ/ffprobe"

cat > "${PACKAGE_ROOT}/DEBIAN/control" <<EOF
Package: ${PACKAGE_NAME}
Version: ${VERSION}
Section: video
Priority: optional
Architecture: ${DEB_ARCH}
Maintainer: Thomas Lothian
Depends: libgtk-4-1 (>= 4.10), libadwaita-1-0 (>= 1.4), libjson-glib-1.0-0
Description: Artwork + Tracks Into Video
 Create an H.264/AAC social video from a still image and audio recording.
EOF

DEB="${PACKAGES}/ATIV-${VERSION}-linux-${LABEL}.deb"
rm -f "${DEB}"
if [[ "$PACKAGE_NAME" != ativ ]]; then
  sed -i 's/^Name=ATIV$/Name=ATIV Development/; s/^Icon=com.tlolabs.ativ$/Icon=com.tlolabs.ativ.development/; s/^Exec=ativ$/Exec=ativ-development/' "$PACKAGE_ROOT/usr/share/applications/com.tlolabs.ativ.desktop"
  mv "$PACKAGE_ROOT/usr/share/applications/com.tlolabs.ativ.desktop" "$PACKAGE_ROOT/usr/share/applications/$APP_ID.desktop"
  while IFS= read -r -d '' icon; do mv "$icon" "$(dirname "$icon")/$APP_ID.png"; done < <(find "$PACKAGE_ROOT/usr/share/icons" -name com.tlolabs.ativ.png -print0)
fi
"$ROOT_DIR/script/package_appimage.sh" "$ARCH" "$PACKAGE_ROOT" "$VERSION"
if [[ "$PACKAGE_NAME" != ativ ]]; then
  mv "$PACKAGE_ROOT/usr/bin/ativ" "$PACKAGE_ROOT/usr/bin/ativ-development"
  mv "$PACKAGE_ROOT/usr/lib/ativ" "$PACKAGE_ROOT/usr/lib/ativ-development"
  mv "$PACKAGE_ROOT/usr/share/doc/ativ" "$PACKAGE_ROOT/usr/share/doc/ativ-development"
  sed -i 's/com.tlolabs.ativ/com.tlolabs.ativ.development/g' "$PACKAGE_ROOT/usr/share/metainfo/com.tlolabs.ativ.metainfo.xml"
  mv "$PACKAGE_ROOT/usr/share/metainfo/com.tlolabs.ativ.metainfo.xml" "$PACKAGE_ROOT/usr/share/metainfo/$APP_ID.metainfo.xml"
fi
dpkg-deb --root-owner-group --build "$PACKAGE_ROOT" "$DEB"
dpkg-deb --info "$DEB"
python3 "$ROOT_DIR/script/validate_package.py" "$PACKAGE_ROOT" "linux-$LABEL-deb"
printf '%s\n' "$DEB"
