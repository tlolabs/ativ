#!/usr/bin/env bash
# Local qualification package only. Never invoked by the application release workflow.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNTIME="${1:?usage: package_core_candidate_macos.sh <validated Core runtime> [existing app template]}"
ARCH="$(uname -m)"
TARGET="macos-$ARCH"
TEMPLATE="${2:-$ROOT/build/package-macos-$ARCH/ATIV.app}"
PYTHON="${PYTHON:-python3}"
CORE="$($PYTHON -c 'import sys;sys.path.insert(0,sys.argv[1]);from acquire_core_runtime import check_core;print(check_core())' "$ROOT/script")"
$PYTHON "$CORE/scripts/ffmpeg/host.py" verify "$TARGET" "$RUNTIME" --candidate
[[ -d "$TEMPLATE/Contents/MacOS" ]] || { echo 'An existing native app template is required.' >&2; exit 1; }
WORK="$ROOT/build/runtime-qualification"
mkdir -p "$WORK"
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export MACOSX_DEPLOYMENT_TARGET=13.0
cargo build --manifest-path "$ROOT/Cargo.toml" --locked --release -p ativ-engine --features managed-runtime --target-dir "$WORK/rust"
swift build --package-path "$ROOT/platform/macos" --scratch-path "$WORK/swift" --configuration release --arch "$ARCH"
SWIFT_BIN="$(swift build --package-path "$ROOT/platform/macos" --scratch-path "$WORK/swift" --configuration release --arch "$ARCH" --show-bin-path)/ATIV"
STAGE="$(mktemp -d "$WORK/package.XXXXXX")"
APP="$STAGE/ATIV Runtime Qualification.app"
ditto "$TEMPLATE" "$APP"
MACOS="$APP/Contents/MacOS"
RESOURCES="$APP/Contents/Resources"
# These paths are copies inside the new temporary package, never the template.
rm "$MACOS/ffmpeg" "$MACOS/ffprobe"
rm -f "$RESOURCES/FFMPEG_LICENSE.txt" "$RESOURCES/FFMPEG_BUILD_CONFIGURATION.txt"
cp "$WORK/rust/release/ativ-engine" "$MACOS/ativ-engine"
cp "$SWIFT_BIN" "$MACOS/ATIV"
$PYTHON "$CORE/scripts/ffmpeg/host.py" stage "$TARGET" "$RUNTIME" --destination "$MACOS" --candidate
$PYTHON - "$APP" <<'PY'
import json,plistlib,sys
from pathlib import Path
app=Path(sys.argv[1]);path=app/'Contents/Info.plist';info=plistlib.loads(path.read_bytes())
info['CFBundleIdentifier']+='.runtimequalification'
info['CFBundleName']='ATIV Runtime Qualification'
info['SUEnableAutomaticChecks']=False
path.write_bytes(plistlib.dumps(info))
(app/'Contents/Resources/RUNTIME_QUALIFICATION_ONLY.json').write_text(json.dumps({'distribution':'local candidate; not an application release','source_information':'FFmpeg/SOURCE.json','runtime_notices':'FFmpeg/licenses/','original_runtime_layout':{'executables':'Contents/MacOS/','metadata_and_notices':'Contents/Resources/FFmpeg/'}},indent=2)+'\n')
PY
# Verify original hashes immediately before changing either executable's signature.
$PYTHON "$CORE/scripts/ffmpeg/host.py" verify "$TARGET" "$MACOS" --candidate
# Sign executable helpers before relocating verified data to the resource directory.
for NAME in ffmpeg ffprobe ativ-engine; do codesign --force --options runtime --sign - "$MACOS/$NAME"; done
$PYTHON "$CORE/scripts/ffmpeg/host.py" record-signed "$TARGET" "$MACOS"
mkdir -p "$RESOURCES/FFmpeg"
for SOURCE in "$RUNTIME"/*; do
  NAME="${SOURCE##*/}"
  case "$NAME" in
    ffmpeg|ffprobe) ;;
    *) mv "$MACOS/$NAME" "$RESOURCES/FFmpeg/$NAME" ;;
  esac
done
mv "$MACOS/signed-payload.json" "$RESOURCES/FFmpeg/signed-payload.json"
codesign --force --options runtime --sign - "$APP"
codesign --verify --deep --strict "$APP"
PATH='' "$MACOS/ativ-engine" check
$PYTHON "$ROOT/script/test_engine_contract.py" --engine "$MACOS/ativ-engine" --ffmpeg "$MACOS/ffmpeg" --ffprobe "$MACOS/ffprobe" --managed
$PYTHON "$ROOT/script/create_smoke_media.py" "$WORK/native-fixtures"
ATIV_TEST_MEDIA="$WORK/native-fixtures" ATIV_ENGINE_PATH="$MACOS/ativ-engine" \
  swift test --package-path "$ROOT/platform/macos" --scratch-path "$WORK/native-tests"
printf '%s\n' "$APP"
