#!/usr/bin/env bash
set -euo pipefail
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export MACOSX_DEPLOYMENT_TARGET=13.0

MODE="${1:-run}"
APP_NAME="ATIV"
BUNDLE_ID="com.tlolabs.ativ"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_BUNDLE="${ROOT_DIR}/dist/${APP_NAME}.app"
APP_CONTENTS="${APP_BUNDLE}/Contents"
APP_MACOS="${APP_CONTENTS}/MacOS"
APP_RESOURCES="${APP_CONTENTS}/Resources"
SWIFT_BUILD_DIR="${ROOT_DIR}/build/native-swift"
RUNTIME_TARGET="macos-$(uname -m)"
RUNTIME="$(python3 "$ROOT_DIR/script/core_runtime.py" provision "$RUNTIME_TARGET")"

pkill -x "${APP_NAME}" >/dev/null 2>&1 || true

cargo build --manifest-path "${ROOT_DIR}/Cargo.toml" -p ativ-engine
swift build --package-path "${ROOT_DIR}/platform/macos" --scratch-path "${SWIFT_BUILD_DIR}"
SWIFT_BIN_DIR="$(swift build --package-path "${ROOT_DIR}/platform/macos" --scratch-path "${SWIFT_BUILD_DIR}" --show-bin-path)"

rm -rf "${APP_BUNDLE}"
mkdir -p "${APP_MACOS}" "${APP_RESOURCES}"
cp "${SWIFT_BIN_DIR}/${APP_NAME}" "${APP_MACOS}/${APP_NAME}"
cp "${ROOT_DIR}/target/debug/ativ-engine" "${APP_MACOS}/ativ-engine"
python3 "$ROOT_DIR/script/core_runtime.py" stage "$RUNTIME_TARGET" --runtime "$RUNTIME" --binary "$APP_MACOS"
cp "${ROOT_DIR}/platform/macos/Info.plist" "${APP_CONTENTS}/Info.plist"
cp "${ROOT_DIR}/platform/macos/Resources/ATIV.icns" "${APP_RESOURCES}/ATIV.icns"
cp "${ROOT_DIR}/LICENSE" "${APP_RESOURCES}/LICENSE"
cp "${ROOT_DIR}/THIRD_PARTY_NOTICES.md" "${APP_RESOURCES}/THIRD_PARTY_NOTICES.md"
cp "${ROOT_DIR}/../AVID Core/LICENSE" "${APP_RESOURCES}/AVID_CORE_LICENSE.txt"
chmod +x "${APP_MACOS}/${APP_NAME}" "${APP_MACOS}/ativ-engine" "${APP_MACOS}/ffmpeg" "${APP_MACOS}/ffprobe"
for NAME in ffmpeg ffprobe ativ-engine; do codesign --force --options runtime --sign - "$APP_MACOS/$NAME"; done
python3 "$ROOT_DIR/script/core_runtime.py" finish "$RUNTIME_TARGET" --binary "$APP_MACOS" --metadata "$APP_RESOURCES/FFmpeg"
"${APP_MACOS}/ativ-engine" check

LABEL="$(uname -m)"; [[ "$LABEL" != x86_64 ]] || LABEL=intel
python3 "$ROOT_DIR/script/configure_distribution.py" "$APP_MACOS" "macos-$LABEL"
FRAMEWORK="$("$ROOT_DIR/script/prepare_sparkle.sh")"
mkdir -p "$APP_CONTENTS/Frameworks"
ditto "$FRAMEWORK" "$APP_CONTENTS/Frameworks/Sparkle.framework"
cp "$(dirname "$FRAMEWORK")/LICENSE" "$APP_RESOURCES/SPARKLE_LICENSE.txt"
# Sign nested Sparkle code without re-signing the already recorded media tools.
while IFS= read -r -d '' nested; do codesign --force --sign - "$nested"; done < <(find "$APP_CONTENTS/Frameworks" -depth \( -name '*.xpc' -o -name '*.app' -o -name '*.framework' -o -name Autoupdate \) -print0)
codesign --force --sign - "${APP_MACOS}/ATIV"
codesign --force --sign - "${APP_BUNDLE}" >/dev/null
python3 "$ROOT_DIR/script/validate_package.py" "$APP_BUNDLE" "macos-$LABEL"

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
