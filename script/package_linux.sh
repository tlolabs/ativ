#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="${1:-$(uname -m)}"
FFMPEG_DIR="${2:-${ROOT_DIR}/build/ffmpeg-linux-${ARCH}}"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "${ROOT_DIR}/Cargo.toml" | head -n 1)"

case "${ARCH}" in
  x86_64) DEB_ARCH="amd64" ;;
  aarch64|arm64) ARCH="aarch64"; DEB_ARCH="arm64" ;;
  *) echo "unsupported Linux architecture: ${ARCH}" >&2; exit 2 ;;
esac
[[ "$(uname -m)" == "${ARCH}" || ( "$(uname -m)" == "arm64" && "${ARCH}" == "aarch64" ) ]] || { echo "Run on a native ${ARCH} Linux runner." >&2; exit 2; }
[[ -x "${FFMPEG_DIR}/ffmpeg" && -x "${FFMPEG_DIR}/ffprobe" ]]
"${FFMPEG_DIR}/ffmpeg" -version | head -n 1 | grep -F "ffmpeg version n9.0.1"

BUILD_DIR="${ROOT_DIR}/build/linux-${ARCH}"
PACKAGE_ROOT="${ROOT_DIR}/build/package-linux-${ARCH}"
PACKAGES="${ROOT_DIR}/packages"
rm -rf "${BUILD_DIR}" "${PACKAGE_ROOT}"
mkdir -p "${PACKAGE_ROOT}/DEBIAN" "${PACKAGE_ROOT}/usr/lib/ativ" "${PACKAGE_ROOT}/usr/share/doc/ativ" "${PACKAGES}"

cargo build --manifest-path "${ROOT_DIR}/Cargo.toml" --release --locked -p ativ-engine
meson setup "${BUILD_DIR}" "${ROOT_DIR}/platform/linux" --prefix=/usr -Dengine_path=/usr/lib/ativ/ativ-engine
meson compile -C "${BUILD_DIR}"
DESTDIR="${PACKAGE_ROOT}" meson install -C "${BUILD_DIR}"
cp "${ROOT_DIR}/target/release/ativ-engine" "${PACKAGE_ROOT}/usr/lib/ativ/ativ-engine"
cp "${FFMPEG_DIR}/ffmpeg" "${PACKAGE_ROOT}/usr/lib/ativ/ffmpeg"
cp "${FFMPEG_DIR}/ffprobe" "${PACKAGE_ROOT}/usr/lib/ativ/ffprobe"
cp "${ROOT_DIR}/LICENSE" "${PACKAGE_ROOT}/usr/share/doc/ativ/LICENSE"
cp "${ROOT_DIR}/THIRD_PARTY_NOTICES.md" "${PACKAGE_ROOT}/usr/share/doc/ativ/THIRD_PARTY_NOTICES.md"
if [[ -f "${FFMPEG_DIR}/FFMPEG_LICENSE.txt" ]]; then cp "${FFMPEG_DIR}/FFMPEG_LICENSE.txt" "${PACKAGE_ROOT}/usr/share/doc/ativ/"; fi
"${PACKAGE_ROOT}/usr/lib/ativ/ffmpeg" -buildconf > "${PACKAGE_ROOT}/usr/share/doc/ativ/FFMPEG_BUILD_CONFIGURATION.txt" 2>&1
chmod 0755 "${PACKAGE_ROOT}/usr/bin/ativ" "${PACKAGE_ROOT}/usr/lib/ativ/ativ-engine" "${PACKAGE_ROOT}/usr/lib/ativ/ffmpeg" "${PACKAGE_ROOT}/usr/lib/ativ/ffprobe"

cat > "${PACKAGE_ROOT}/DEBIAN/control" <<EOF
Package: ativ
Version: ${VERSION}
Section: video
Priority: optional
Architecture: ${DEB_ARCH}
Maintainer: A.T.I.V. maintainers <opensource@tlolabs.com>
Depends: libgtk-4-1 (>= 4.10), libadwaita-1-0 (>= 1.5), libjson-glib-1.0-0
Description: Audio Visual Integration & Distribution
 Create an H.264/AAC social video from a still image and audio recording.
EOF

DEB="${PACKAGES}/ativ_${VERSION}_${DEB_ARCH}.deb"
TAR="${PACKAGES}/ativ-${VERSION}-linux-${ARCH}.tar.gz"
rm -f "${DEB}" "${TAR}"
dpkg-deb --root-owner-group --build "${PACKAGE_ROOT}" "${DEB}"
tar -C "${PACKAGE_ROOT}" -czf "${TAR}" usr
printf '%s\n%s\n' "${DEB}" "${TAR}"
