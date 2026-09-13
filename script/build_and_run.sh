#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-run}"
APP_NAME="AVID"
BUNDLE_ID="AVID"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_BUNDLE="${ROOT_DIR}/dist/${APP_NAME}.app"
APP_CONTENTS="${APP_BUNDLE}/Contents"
APP_MACOS="${APP_CONTENTS}/MacOS"
APP_RESOURCES="${APP_CONTENTS}/Resources"
SWIFT_BUILD_DIR="${ROOT_DIR}/build/native-swift"
FFMPEG_BIN="${FFMPEG_BIN:-$(command -v ffmpeg || true)}"
FFPROBE_BIN="${FFPROBE_BIN:-$(command -v ffprobe || true)}"

if [[ ! -x "${FFMPEG_BIN}" || ! -x "${FFPROBE_BIN}" ]]; then
  echo "FFmpeg and ffprobe are required for a local A.V.I.D. build." >&2
  exit 1
fi

pkill -x "${APP_NAME}" >/dev/null 2>&1 || true

cargo build --manifest-path "${ROOT_DIR}/Cargo.toml" -p avid-engine
swift build --package-path "${ROOT_DIR}/platform/macos" --scratch-path "${SWIFT_BUILD_DIR}"
SWIFT_BIN_DIR="$(swift build --package-path "${ROOT_DIR}/platform/macos" --scratch-path "${SWIFT_BUILD_DIR}" --show-bin-path)"

rm -rf "${APP_BUNDLE}"
mkdir -p "${APP_MACOS}" "${APP_RESOURCES}"
cp "${SWIFT_BIN_DIR}/${APP_NAME}" "${APP_MACOS}/${APP_NAME}"
cp "${ROOT_DIR}/target/debug/avid-engine" "${APP_MACOS}/avid-engine"
cp "${FFMPEG_BIN}" "${APP_MACOS}/ffmpeg"
cp "${FFPROBE_BIN}" "${APP_MACOS}/ffprobe"
cp "${ROOT_DIR}/platform/macos/Info.plist" "${APP_CONTENTS}/Info.plist"
cp "${ROOT_DIR}/platform/macos/Resources/icon-windowed.icns" "${APP_RESOURCES}/icon-windowed.icns"
cp "${ROOT_DIR}/LICENSE" "${APP_RESOURCES}/LICENSE"
cp "${ROOT_DIR}/THIRD_PARTY_NOTICES.md" "${APP_RESOURCES}/THIRD_PARTY_NOTICES.md"
chmod +x "${APP_MACOS}/${APP_NAME}" "${APP_MACOS}/avid-engine" "${APP_MACOS}/ffmpeg" "${APP_MACOS}/ffprobe"
codesign --force --deep --sign - "${APP_BUNDLE}" >/dev/null

open_app() { /usr/bin/open -n "${APP_BUNDLE}"; }

case "${MODE}" in
  run) open_app ;;
  --debug|debug) lldb -- "${APP_MACOS}/${APP_NAME}" ;;
  --logs|logs)
    open_app
    /usr/bin/log stream --info --style compact --predicate "process == \"${APP_NAME}\""
    ;;
  --telemetry|telemetry)
    open_app
    /usr/bin/log stream --info --style compact --predicate "subsystem == \"${BUNDLE_ID}\""
    ;;
  --verify|verify)
    open_app
    sleep 1
    pgrep -x "${APP_NAME}" >/dev/null
    ;;
  *) echo "usage: $0 [run|--debug|--logs|--telemetry|--verify]" >&2; exit 2 ;;
esac
