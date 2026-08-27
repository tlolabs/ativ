#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCH="${1:-arm64}"

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

pyinstaller \
  --noconfirm \
  --windowed \
  --target-arch "${ARCH}" \
  --name AVID \
  --specpath "${ROOT_DIR}" \
  --workpath "${ROOT_DIR}/build/${ARCH}" \
  --distpath "${ROOT_DIR}/dist/${ARCH}" \
  --add-data "LICENSE:." \
  --add-binary "${FFMPEG_BIN}:." \
  --add-binary "${FFPROBE_BIN}:." \
  avid_gui.py

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
