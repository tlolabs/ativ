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
  x86_64) : ;;
  aarch64|arm64) ARCH="aarch64"; LABEL=arm64 ;;
  *) echo "unsupported Linux architecture: ${ARCH}" >&2; exit 2 ;;
esac
[[ "$(uname -m)" == "${ARCH}" || ( "$(uname -m)" == "arm64" && "${ARCH}" == "aarch64" ) ]] || { echo "Run on a native ${ARCH} Linux runner." >&2; exit 2; }
RUNTIME_TARGET="linux-$ARCH"
RUNTIME="$(python3 "$ROOT_DIR/script/ffmpeg_runtime.py" provision "$RUNTIME_TARGET")"

BUILD_DIR="${ROOT_DIR}/build/linux-${ARCH}"
PACKAGE_ROOT="${ROOT_DIR}/build/package-linux-${ARCH}"
PACKAGES="${ROOT_DIR}/packages"
rm -rf "${BUILD_DIR}" "${PACKAGE_ROOT}"
mkdir -p "${PACKAGE_ROOT}/usr/lib/ativ" "${PACKAGE_ROOT}/usr/share/doc/ativ" "${PACKAGES}"

cargo build --manifest-path "${ROOT_DIR}/Cargo.toml" --release --locked -p ativ-engine -p ativ-update

cmake -S "${ROOT_DIR}/platform/qt" -B "${BUILD_DIR}/cmake" -DCMAKE_BUILD_TYPE=Release
cmake --build "${BUILD_DIR}/cmake" --parallel
cp "${BUILD_DIR}/cmake/ATIV" "${PACKAGE_ROOT}/usr/lib/ativ/ATIV"

QT_PLUGINS_DIR="$(qmake6 -query QT_INSTALL_PLUGINS 2>/dev/null || echo "/usr/lib/$(uname -m)-linux-gnu/qt6/plugins")"
if [[ -d "${QT_PLUGINS_DIR}/platforms" ]]; then
  mkdir -p "${PACKAGE_ROOT}/usr/lib/ativ/plugins/platforms"
  cp -a "${QT_PLUGINS_DIR}/platforms/"*.so "${PACKAGE_ROOT}/usr/lib/ativ/plugins/platforms/" 2>/dev/null || true
  cat > "${PACKAGE_ROOT}/usr/lib/ativ/qt.conf" <<EOF
[Paths]
Prefix = ..
Plugins = lib/ativ/plugins
EOF
fi

install -Dm755 "${ROOT_DIR}/platform/linux/ativ-launcher" "${PACKAGE_ROOT}/usr/bin/ativ"
install -Dm644 "${ROOT_DIR}/platform/linux/data/com.tlolabs.ativ.desktop" "${PACKAGE_ROOT}/usr/share/applications/com.tlolabs.ativ.desktop"
install -Dm644 "${ROOT_DIR}/platform/linux/data/com.tlolabs.ativ.metainfo.xml" "${PACKAGE_ROOT}/usr/share/metainfo/com.tlolabs.ativ.metainfo.xml"
for size in 16 24 32 48 64 128 256 512; do install -Dm644 "${ROOT_DIR}/platform/linux/data/icons/$size.png" "${PACKAGE_ROOT}/usr/share/icons/hicolor/${size}x${size}/apps/com.tlolabs.ativ.png"; done
cp "${ROOT_DIR}/target/release/ativ-engine" "${PACKAGE_ROOT}/usr/lib/ativ/ativ-engine"
cp "${ROOT_DIR}/target/release/ativ-update" "${PACKAGE_ROOT}/usr/lib/ativ/ativ-update"
python3 "$ROOT_DIR/script/configure_distribution.py" "$PACKAGE_ROOT/usr/lib/ativ" "linux-$LABEL-deb"
python3 "$ROOT_DIR/script/ffmpeg_runtime.py" stage "$RUNTIME_TARGET" --runtime "$RUNTIME" --binary "$PACKAGE_ROOT/usr/lib/ativ"
python3 "$ROOT_DIR/script/ffmpeg_runtime.py" finish "$RUNTIME_TARGET" --binary "$PACKAGE_ROOT/usr/lib/ativ" --metadata "$PACKAGE_ROOT/usr/lib/ativ/ffmpeg-runtime"
cp "${ROOT_DIR}/LICENSE" "${PACKAGE_ROOT}/usr/share/doc/ativ/LICENSE"
cp "${ROOT_DIR}/THIRD_PARTY_NOTICES.md" "${PACKAGE_ROOT}/usr/share/doc/ativ/THIRD_PARTY_NOTICES.md"
python3 "$ROOT_DIR/script/collect_licenses.py" "$PACKAGE_ROOT/usr/share/doc/ativ/licenses"
chmod 0755 "${PACKAGE_ROOT}/usr/bin/ativ" "${PACKAGE_ROOT}/usr/lib/ativ/ativ-engine" "${PACKAGE_ROOT}/usr/lib/ativ/ffmpeg" "${PACKAGE_ROOT}/usr/lib/ativ/ffprobe"

if [[ "$PACKAGE_NAME" != ativ ]]; then
  install -Dm755 "${ROOT_DIR}/platform/linux/ativ-launcher" "${PACKAGE_ROOT}/usr/bin/ativ-development"
  sed -i 's/^Name=ATIV$/Name=ATIV Development/; s/^Icon=com.tlolabs.ativ$/Icon=com.tlolabs.ativ.development/; s/^Exec=ativ$/Exec=ativ-development/' "$PACKAGE_ROOT/usr/share/applications/com.tlolabs.ativ.desktop"
  mv "$PACKAGE_ROOT/usr/share/applications/com.tlolabs.ativ.desktop" "$PACKAGE_ROOT/usr/share/applications/$APP_ID.desktop"
  while IFS= read -r -d '' icon; do mv "$icon" "$(dirname "$icon")/$APP_ID.png"; done < <(find "$PACKAGE_ROOT/usr/share/icons" -name com.tlolabs.ativ.png -print0)
fi
"$ROOT_DIR/script/package_appimage.sh" "$ARCH" "$PACKAGE_ROOT" "$VERSION"
printf '%s\n' "$PACKAGES/ATIV-$VERSION-linux-$LABEL.AppImage"
