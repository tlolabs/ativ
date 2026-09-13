#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/avid integration ü.XXXXXX")"
trap 'rm -rf "${WORK_DIR}"' EXIT
MEDIA_DIR="${WORK_DIR}/media with spaces"
ENGINE="${ROOT_DIR}/target/debug/avid-engine"
mkdir -p "${MEDIA_DIR}"

cargo build --manifest-path "${ROOT_DIR}/Cargo.toml" --locked -p avid-engine
ffmpeg -hide_banner -loglevel error -f lavfi -i color=c=0x355070:s=640x360 -frames:v 1 "${MEDIA_DIR}/cover art.png"
ffmpeg -hide_banner -loglevel error -f lavfi -i sine=frequency=523:duration=2 -c:a pcm_s16le "${MEDIA_DIR}/voice track.wav"

"${ENGINE}" check | grep -F '"event":"tools"'
"${ENGINE}" presets | grep -F '"event":"presets"'
"${ENGINE}" probe --audio "${MEDIA_DIR}/voice track.wav" | grep -F '"event":"probe"'
"${ENGINE}" preview --image "${MEDIA_DIR}/cover art.png" --output "${MEDIA_DIR}/preview image.png" --width 320 --height 180
test -s "${MEDIA_DIR}/preview image.png"

"${ENGINE}" render --image "${MEDIA_DIR}/cover art.png" --audio "${MEDIA_DIR}/voice track.wav" --output "${MEDIA_DIR}/finished video.mp4" --width 320 --height 180 --fps 30 --audio-bitrate 128k | grep -F '"stage":"complete"'
test "$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "${MEDIA_DIR}/finished video.mp4")" = "h264"
test "$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "${MEDIA_DIR}/finished video.mp4")" = "aac"

printf 'existing output must survive\n' > "${MEDIA_DIR}/preserved.mp4"
set +e
printf 'cancel\n' | "${ENGINE}" render --image "${MEDIA_DIR}/cover art.png" --audio "${MEDIA_DIR}/voice track.wav" --output "${MEDIA_DIR}/preserved.mp4" --width 1920 --height 1080 >/dev/null
STATUS=$?
set -e
test "${STATUS}" -eq 130
grep -F 'existing output must survive' "${MEDIA_DIR}/preserved.mp4"
test -z "$(find "${MEDIA_DIR}" -maxdepth 1 -name '.avid-*.tmp.*' -print -quit)"

echo "Engine integration checks passed."
