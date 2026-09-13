#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="${1:-$(uname -m)}"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "${ROOT_DIR}/Cargo.toml" | head -n 1)"
: "${FFMPEG_BIN:?Set FFMPEG_BIN to the checksum-verified FFmpeg executable.}"
: "${FFPROBE_BIN:?Set FFPROBE_BIN to the checksum-verified ffprobe executable.}"
SIGN_IDENTITY="${APPLE_SIGN_IDENTITY:--}"

case "${ARCH}" in
  arm64|aarch64) ARCH="arm64"; RUST_TARGET="aarch64-apple-darwin" ;;
  x86_64) RUST_TARGET="x86_64-apple-darwin" ;;
  *) echo "unsupported macOS architecture: ${ARCH}" >&2; exit 2 ;;
esac
[[ "$(uname -m)" == "${ARCH}" ]] || { echo "Run this packaging script on a native ${ARCH} macOS runner." >&2; exit 2; }
[[ -x "${FFMPEG_BIN}" && -x "${FFPROBE_BIN}" ]] || { echo "FFmpeg and ffprobe are required." >&2; exit 1; }
"${FFMPEG_BIN}" -version | head -n 1 | grep -F "ffmpeg version 9.0.1"

verify_system_dependencies() {
  local binary="$1"
  local unexpected
  unexpected="$(otool -L "${binary}" | tail -n +2 | awk '{print $1}' | grep -Ev '^(/System/Library/|/usr/lib/)' || true)"
  [[ -z "${unexpected}" ]] || {
    echo "${binary} has non-system dynamic dependencies:" >&2
    echo "${unexpected}" >&2
    exit 1
  }
}
verify_system_dependencies "${FFMPEG_BIN}"
verify_system_dependencies "${FFPROBE_BIN}"

APP="${ROOT_DIR}/build/package-macos-${ARCH}/AVID.app"
CONTENTS="${APP}/Contents"
MACOS="${CONTENTS}/MacOS"
RESOURCES="${CONTENTS}/Resources"
SWIFT_BUILD="${ROOT_DIR}/build/swift-release-${ARCH}"
PACKAGES="${ROOT_DIR}/packages"

rustup target add "${RUST_TARGET}"
cargo build --manifest-path "${ROOT_DIR}/Cargo.toml" --release --locked --target "${RUST_TARGET}" -p avid-engine
swift build --package-path "${ROOT_DIR}/platform/macos" --scratch-path "${SWIFT_BUILD}" -c release --arch "${ARCH}"
SWIFT_BIN="$(swift build --package-path "${ROOT_DIR}/platform/macos" --scratch-path "${SWIFT_BUILD}" -c release --arch "${ARCH}" --show-bin-path)/AVID"

rm -rf "${APP}"
mkdir -p "${MACOS}" "${RESOURCES}" "${PACKAGES}"
cp "${SWIFT_BIN}" "${MACOS}/AVID"
cp "${ROOT_DIR}/target/${RUST_TARGET}/release/avid-engine" "${MACOS}/avid-engine"
cp "${FFMPEG_BIN}" "${MACOS}/ffmpeg"
cp "${FFPROBE_BIN}" "${MACOS}/ffprobe"
cp "${ROOT_DIR}/platform/macos/Info.plist" "${CONTENTS}/Info.plist"
cp "${ROOT_DIR}/platform/macos/Resources/icon-windowed.icns" "${RESOURCES}/icon-windowed.icns"
cp "${ROOT_DIR}/LICENSE" "${RESOURCES}/LICENSE"
cp "${ROOT_DIR}/THIRD_PARTY_NOTICES.md" "${RESOURCES}/THIRD_PARTY_NOTICES.md"
"${MACOS}/ffmpeg" -buildconf > "${RESOURCES}/FFMPEG_BUILD_CONFIGURATION.txt" 2>&1
cp "${FFMPEG_LICENSE_FILE:-${ROOT_DIR}/LICENSE}" "${RESOURCES}/FFMPEG_LICENSE.txt"
chmod +x "${MACOS}/AVID" "${MACOS}/avid-engine" "${MACOS}/ffmpeg" "${MACOS}/ffprobe"

SIGN_ARGS=(--force --options runtime --sign "${SIGN_IDENTITY}")
if [[ "${SIGN_IDENTITY}" != "-" ]]; then SIGN_ARGS+=(--timestamp); fi
codesign "${SIGN_ARGS[@]}" "${MACOS}/avid-engine"
codesign "${SIGN_ARGS[@]}" "${MACOS}/ffmpeg"
codesign "${SIGN_ARGS[@]}" "${MACOS}/ffprobe"
codesign "${SIGN_ARGS[@]}" "${MACOS}/AVID"
codesign --deep "${SIGN_ARGS[@]}" "${APP}"
codesign --verify --deep --strict "${APP}"

ZIP="${PACKAGES}/AVID-${VERSION}-macos-${ARCH}.zip"
DMG="${PACKAGES}/AVID-${VERSION}-macos-${ARCH}.dmg"
rm -f "${ZIP}" "${DMG}"
ditto -c -k --sequesterRsrc --keepParent "${APP}" "${ZIP}"
hdiutil create -quiet -volname "A.V.I.D. ${VERSION}" -srcfolder "${APP}" -ov -format UDZO "${DMG}"

if [[ -n "${APPLE_NOTARY_PROFILE:-}" ]]; then
  xcrun notarytool submit "${DMG}" --keychain-profile "${APPLE_NOTARY_PROFILE}" --wait
  xcrun stapler staple "${DMG}"
  spctl --assess --type open --context context:primary-signature -v "${DMG}"
elif [[ "${SIGN_IDENTITY}" != "-" ]]; then
  echo "APPLE_NOTARY_PROFILE is not set; signed artifacts were not notarized." >&2
fi

printf '%s\n%s\n' "${ZIP}" "${DMG}"
