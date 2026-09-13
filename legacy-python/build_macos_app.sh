#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCH="${1:-arm64}"
MACOS_SIGNING_IDENTITY="${MACOS_SIGNING_IDENTITY:-}"
MACOS_NOTARY_PROFILE="${MACOS_NOTARY_PROFILE:-}"
AVID_REQUIRE_SIGNED_RELEASE="${AVID_REQUIRE_SIGNED_RELEASE:-0}"

case "${ARCH}" in
  arm64)
    FFMPEG_BIN="${FFMPEG_BIN:-/opt/homebrew/bin/ffmpeg}"
    FFPROBE_BIN="${FFPROBE_BIN:-/opt/homebrew/bin/ffprobe}"
    ;;
  x86_64)
    FFMPEG_BIN="${FFMPEG_BIN:-/usr/local/bin/ffmpeg}"
    FFPROBE_BIN="${FFPROBE_BIN:-/usr/local/bin/ffprobe}"
    ;;
  *)
    echo "Unsupported macOS architecture: ${ARCH}" >&2
    echo "Usage: $0 [arm64|x86_64]" >&2
    exit 1
    ;;
esac

if [[ "${AVID_REQUIRE_SIGNED_RELEASE}" == "1" && -z "${MACOS_SIGNING_IDENTITY}" ]]; then
  echo "MACOS_SIGNING_IDENTITY is required for a signed release build." >&2
  exit 1
fi
if [[ "${AVID_REQUIRE_SIGNED_RELEASE}" == "1" && -z "${MACOS_NOTARY_PROFILE}" ]]; then
  echo "MACOS_NOTARY_PROFILE is required for a notarized release build." >&2
  exit 1
fi
if [[ -n "${MACOS_NOTARY_PROFILE}" && -z "${MACOS_SIGNING_IDENTITY}" ]]; then
  echo "MACOS_SIGNING_IDENTITY is required when MACOS_NOTARY_PROFILE is set." >&2
  exit 1
fi

if [[ ! -x "${FFMPEG_BIN}" ]]; then
  echo "Missing executable FFmpeg binary: ${FFMPEG_BIN}" >&2
  exit 1
fi

if [[ ! -x "${FFPROBE_BIN}" ]]; then
  echo "Missing executable ffprobe binary: ${FFPROBE_BIN}" >&2
  exit 1
fi

if [[ -f "${ROOT_DIR}/.venv/bin/activate" ]]; then
  source "${ROOT_DIR}/.venv/bin/activate"
fi
export PYINSTALLER_CONFIG_DIR="${ROOT_DIR}/.pyinstaller"

PYINSTALLER_ARGS=(
  --noconfirm
  --windowed
  --target-arch "${ARCH}"
  --name AVID
  --specpath "${ROOT_DIR}"
  --workpath "${ROOT_DIR}/build/${ARCH}"
  --distpath "${ROOT_DIR}/dist/${ARCH}"
  --add-data "${ROOT_DIR}/LICENSE:."
  --add-binary "${FFMPEG_BIN}:."
  --add-binary "${FFPROBE_BIN}:."
)
if [[ -n "${MACOS_SIGNING_IDENTITY}" ]]; then
  PYINSTALLER_ARGS+=(--codesign-identity "${MACOS_SIGNING_IDENTITY}")
fi

pyinstaller "${PYINSTALLER_ARGS[@]}" "${ROOT_DIR}/avid_gui.py"

APP_PATH="${ROOT_DIR}/dist/${ARCH}/AVID.app"
python "${ROOT_DIR}/check_ffmpeg_bundle.py" \
  --root "${APP_PATH}" \
  --platform darwin \
  --arch "${ARCH}" \
  --require-bundled-ffmpeg
if [[ -n "${MACOS_SIGNING_IDENTITY}" ]]; then
  codesign --verify --deep --strict --verbose=2 "${APP_PATH}"
fi

mkdir -p "${ROOT_DIR}/packages/dmg-root"
rm -rf "${ROOT_DIR}/packages/dmg-root/AVID.app"
cp -R "${ROOT_DIR}/dist/${ARCH}/AVID.app" "${ROOT_DIR}/packages/dmg-root/AVID.app"
rm -f "${ROOT_DIR}/packages/AVID-macos-${ARCH}.dmg"
hdiutil create \
  -volname AVID \
  -srcfolder "${ROOT_DIR}/packages/dmg-root" \
  -ov \
  -format UDZO \
  "${ROOT_DIR}/packages/AVID-macos-${ARCH}.dmg"

DMG_PATH="${ROOT_DIR}/packages/AVID-macos-${ARCH}.dmg"
if [[ -n "${MACOS_SIGNING_IDENTITY}" ]]; then
  codesign --force --timestamp --sign "${MACOS_SIGNING_IDENTITY}" "${DMG_PATH}"
  codesign --verify --strict --verbose=2 "${DMG_PATH}"
fi
if [[ -n "${MACOS_NOTARY_PROFILE}" ]]; then
  xcrun notarytool submit "${DMG_PATH}" --keychain-profile "${MACOS_NOTARY_PROFILE}" --wait
  xcrun stapler staple "${DMG_PATH}"
  xcrun stapler validate "${DMG_PATH}"
  spctl --assess --type open --context context:primary-signature --verbose=2 "${DMG_PATH}"
fi
