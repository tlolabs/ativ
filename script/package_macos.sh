#!/usr/bin/env bash
set -euo pipefail
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export MACOSX_DEPLOYMENT_TARGET=13.0

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="${1:-$(uname -m)}"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "${ROOT_DIR}/Cargo.toml" | head -n 1)"
VERSION="${ATIV_VERSION:-$VERSION}"
SIGN_IDENTITY="${APPLE_SIGN_IDENTITY:--}"

case "${ARCH}" in
  arm64|aarch64) ARCH="arm64"; RUST_TARGET="aarch64-apple-darwin" ;;
  x86_64) RUST_TARGET="x86_64-apple-darwin" ;;
  *) echo "unsupported macOS architecture: ${ARCH}" >&2; exit 2 ;;
esac
[[ "$(uname -m)" == "${ARCH}" ]] || { echo "Run this packaging script on a native ${ARCH} macOS runner." >&2; exit 2; }
RUNTIME="$(python3 "$ROOT_DIR/script/ffmpeg_runtime.py" provision "macos-$ARCH")"

APP="${ROOT_DIR}/build/package-macos-${ARCH}/ATIV.app"
CONTENTS="${APP}/Contents"
MACOS="${CONTENTS}/MacOS"
RESOURCES="${CONTENTS}/Resources"
SWIFT_BUILD="${ROOT_DIR}/build/swift-release-${ARCH}"
PACKAGES="${ROOT_DIR}/packages"

rustup target add "${RUST_TARGET}"
cargo build --manifest-path "${ROOT_DIR}/Cargo.toml" --release --locked --target "${RUST_TARGET}" -p ativ-engine
swift build --package-path "${ROOT_DIR}/platform/macos" --scratch-path "${SWIFT_BUILD}" -c release --arch "${ARCH}"
SWIFT_BIN="$(swift build --package-path "${ROOT_DIR}/platform/macos" --scratch-path "${SWIFT_BUILD}" -c release --arch "${ARCH}" --show-bin-path)/ATIV"

rm -rf "${APP}"
mkdir -p "${MACOS}" "${RESOURCES}" "${PACKAGES}"
cp "${SWIFT_BIN}" "${MACOS}/ATIV"
cp "${ROOT_DIR}/target/${RUST_TARGET}/release/ativ-engine" "${MACOS}/ativ-engine"
python3 "$ROOT_DIR/script/ffmpeg_runtime.py" stage "macos-$ARCH" --runtime "$RUNTIME" --binary "$MACOS"
cp "${ROOT_DIR}/platform/macos/Info.plist" "${CONTENTS}/Info.plist"
cp "${ROOT_DIR}/platform/macos/Resources/ATIV.icns" "${RESOURCES}/ATIV.icns"
cp "${ROOT_DIR}/LICENSE" "${RESOURCES}/LICENSE"
cp "${ROOT_DIR}/THIRD_PARTY_NOTICES.md" "${RESOURCES}/THIRD_PARTY_NOTICES.md"
chmod +x "${MACOS}/ATIV" "${MACOS}/ativ-engine" "${MACOS}/ffmpeg" "${MACOS}/ffprobe"


LABEL="$ARCH"; [[ "$ARCH" != x86_64 ]] || LABEL=intel
python3 "$ROOT_DIR/script/configure_distribution.py" "$MACOS" "macos-$LABEL"
FRAMEWORK="$("$ROOT_DIR/script/prepare_sparkle.sh")"
mkdir -p "$CONTENTS/Frameworks"
ditto "$FRAMEWORK" "$CONTENTS/Frameworks/Sparkle.framework"
cp "$(dirname "$FRAMEWORK")/LICENSE" "$RESOURCES/SPARKLE_LICENSE.txt"
python3 "$ROOT_DIR/script/collect_licenses.py" "$RESOURCES/licenses" --target "$RUST_TARGET"
SIGN_ARGS=(--force --options runtime --sign "${SIGN_IDENTITY}")
if [[ "${SIGN_IDENTITY}" != "-" ]]; then SIGN_ARGS+=(--timestamp); fi
codesign "${SIGN_ARGS[@]}" "${MACOS}/ativ-engine"
codesign "${SIGN_ARGS[@]}" "${MACOS}/ffmpeg"
codesign "${SIGN_ARGS[@]}" "${MACOS}/ffprobe"
codesign "${SIGN_ARGS[@]}" "${MACOS}/ATIV"
# Sign nested Sparkle code inside-out before the enclosing bundle.
while IFS= read -r -d '' nested; do codesign "${SIGN_ARGS[@]}" "$nested"; done < <(find "$CONTENTS/Frameworks" -depth \( -name '*.xpc' -o -name '*.app' -o -name '*.framework' -o -name Autoupdate \) -print0)
python3 "$ROOT_DIR/script/ffmpeg_runtime.py" finish "macos-$ARCH" --binary "$MACOS" --metadata "$RESOURCES/FFmpeg"
codesign "${SIGN_ARGS[@]}" "${APP}"
codesign --verify --deep --strict "${APP}"
python3 "$ROOT_DIR/script/validate_package.py" "$APP" "macos-$LABEL"

LABEL="$ARCH"; [[ "$ARCH" != x86_64 ]] || LABEL=intel
ZIP="${PACKAGES}/ATIV-${VERSION}-macos-${LABEL}.zip"
DMG="${PACKAGES}/ATIV-${VERSION}-macos-${LABEL}.dmg"
rm -f "${ZIP}" "${DMG}"
# Notarize and staple the app before producing the Sparkle archive or DMG.
if [[ -n "${APPLE_NOTARY_PROFILE:-}" ]]; then
  ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
  xcrun notarytool submit "$ZIP" --keychain-profile "$APPLE_NOTARY_PROFILE" --wait
  xcrun stapler staple "$APP"
  xcrun stapler validate "$APP"
fi
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
DMG_STAGE="$ROOT_DIR/build/dmg-$ARCH"
rm -rf "$DMG_STAGE"; mkdir -p "$DMG_STAGE"
APP_DISPLAY=ATIV; [[ "${ATIV_CHANNEL:-stable}" != development ]] || APP_DISPLAY="ATIV Development"
ditto "$APP" "$DMG_STAGE/$APP_DISPLAY.app"
ln -s /Applications "$DMG_STAGE/Applications"
hdiutil create -quiet -volname "$APP_DISPLAY $VERSION" -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG"
if [[ "$SIGN_IDENTITY" != - ]]; then codesign --force --timestamp --sign "$SIGN_IDENTITY" "$DMG"; fi
if [[ -n "${APPLE_NOTARY_PROFILE:-}" ]]; then
  xcrun notarytool submit "$DMG" --keychain-profile "$APPLE_NOTARY_PROFILE" --wait
  xcrun stapler staple "$DMG"
  xcrun stapler validate "$DMG"
fi
hdiutil verify "$DMG"
printf '%s\n%s\n' "$ZIP" "$DMG"
