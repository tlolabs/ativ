#!/usr/bin/env bash
# One-off Qt experiment. Outputs remain under build/, outside release packaging.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:---verify}"
case "$MODE" in --build|--verify|--run) ;; *) echo 'Usage: build_qt_macos.sh [--build|--verify|--run]' >&2; exit 2 ;; esac
[[ "$(uname -s)" == Darwin ]] || { echo 'macOS required' >&2; exit 2; }
# Qt/C++ needs only the Command Line Tools, unlike the production Swift app.
if [[ -z "${DEVELOPER_DIR:-}" && -d /Library/Developer/CommandLineTools ]]; then
    export DEVELOPER_DIR=/Library/Developer/CommandLineTools
fi
QT_PREFIX="${ATIV_QT_PREFIX:-$(qmake6 -query QT_INSTALL_PREFIX)}"
TARGET="macos-$(uname -m)"
OUT="$ROOT/build/qt-macos"
mkdir -p "$OUT"
# Refuse to replace a running experiment, which might be exporting a video.
if pgrep -x 'ATIV Qt' >/dev/null; then echo 'Close ATIV Qt before rebuilding.' >&2; exit 1; fi
RUNTIME="$(python3 "$ROOT/script/ffmpeg_runtime.py" provision "$TARGET")"
cargo build --manifest-path "$ROOT/Cargo.toml" --release --locked -p ativ-engine
cmake -S "$ROOT/platform/qt" -B "$OUT/cmake" -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$QT_PREFIX" -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0
cmake --build "$OUT/cmake" --parallel 4
STAGE="$(mktemp -d "$OUT/stage.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
APP="$STAGE/ATIV Qt.app"
ditto "$OUT/cmake/ATIV Qt.app" "$APP"
# Only Cocoa and the native widget style are needed: previews are PNGs decoded
# by QtGui. Avoid deploying unrelated PDF/SVG plugins from other Qt modules.
PLUGINS="$("$QT_PREFIX/bin/qmake6" -query QT_INSTALL_PLUGINS)"
mkdir -p "$APP/Contents/PlugIns/platforms" "$APP/Contents/PlugIns/styles"
cp "$PLUGINS/platforms/libqcocoa.dylib" "$APP/Contents/PlugIns/platforms/"
cp "$PLUGINS/styles/libqmacstyle.dylib" "$APP/Contents/PlugIns/styles/"
"$QT_PREFIX/bin/macdeployqt" "$APP" -no-plugins -codesign=- \
    -executable="$APP/Contents/PlugIns/platforms/libqcocoa.dylib" \
    -executable="$APP/Contents/PlugIns/styles/libqmacstyle.dylib"
MACOS="$APP/Contents/MacOS"
RESOURCES="$APP/Contents/Resources"
cp "$ROOT/target/release/ativ-engine" "$MACOS/ativ-engine"
python3 "$ROOT/script/ffmpeg_runtime.py" stage "$TARGET" --runtime "$RUNTIME" --binary "$MACOS"
for name in ativ-engine ffmpeg ffprobe; do codesign --force --sign - "$MACOS/$name"; done
python3 "$ROOT/script/ffmpeg_runtime.py" finish "$TARGET" --binary "$MACOS" --metadata "$RESOURCES/FFmpeg"
cp "$ROOT/LICENSE" "$RESOURCES/LICENSE"
cp "$ROOT/THIRD_PARTY_NOTICES.md" "$RESOURCES/THIRD_PARTY_NOTICES.md"
cp "$ROOT/platform/qt/README.md" "$RESOURCES/QT-EXPERIMENT.md"
printf 'ONE-OFF LOCAL QT EXPERIMENT — NOT A PRODUCTION RELEASE\n' > "$RESOURCES/INTERNAL-REFERENCE.txt"
codesign --force --sign - "$APP"
python3 "$ROOT/script/validate_qt_macos.py" "$APP"
ATIV_BUILD_ONLY=1 python3 "$ROOT/script/ffmpeg_runtime.py" validate "$TARGET" --binary "$MACOS" --metadata "$RESOURCES/FFmpeg"
ATIV_QT_TEST_ENGINE="$MACOS/ativ-engine" ctest --test-dir "$OUT/cmake" --output-on-failure
# Replace only the experiment after compilation, bundling, and tests pass.
rm -rf "$OUT/ATIV Qt.app"
mv "$APP" "$OUT/ATIV Qt.app"
APP="$OUT/ATIV Qt.app"
ditto -c -k --keepParent "$APP" "$OUT/ATIV-Qt-$TARGET.zip"
if [[ "$MODE" != --build ]]; then
    /usr/bin/open -n "$APP"
    if [[ "$MODE" == --verify ]]; then sleep 2; pgrep -x 'ATIV Qt' >/dev/null; fi
fi
printf '\n%s\n' "$APP"
