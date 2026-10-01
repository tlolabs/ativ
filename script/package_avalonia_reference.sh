#!/usr/bin/env bash
# Internal-only Apple Silicon reference. Never write to packages/ or release assets.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "$(uname -s)" == Darwin && "$(uname -m)" == arm64 ]] || { echo 'Apple Silicon host required' >&2; exit 2; }
DOTNET="${ATIV_DOTNET:-dotnet}"
VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$ROOT/Cargo.toml" | head -n 1)"
OUT="$ROOT/build/avalonia-reference-macos-arm64"
APP="$OUT/ATIV-Reference.app"
MACOS="$APP/Contents/MacOS"
[[ ! -e "$OUT" ]] || { echo 'Reference output already exists; use a fresh build directory.' >&2; exit 1; }
mkdir -p "$MACOS"
"$DOTNET" publish "$ROOT/platform/avalonia/ATIV.Avalonia.csproj" -c Release -r osx-arm64 --self-contained true -p:Version="$VERSION" -o "$OUT/managed" -warnaserror
cargo build --manifest-path "$ROOT/Cargo.toml" --release --locked -p ativ-engine
cp "$ROOT/target/release/ativ-engine" "$MACOS/ativ-engine"
RUNTIME="$(python3 "$ROOT/script/ffmpeg_runtime.py" provision macos-arm64)"
python3 "$ROOT/script/ffmpeg_runtime.py" stage macos-arm64 --runtime "$RUNTIME" --binary "$MACOS"
python3 "$ROOT/script/ffmpeg_runtime.py" finish macos-arm64 --binary "$MACOS" --metadata "$APP/Contents/Resources/FFmpeg"
cp -a "$OUT/managed/." "$MACOS/"
mkdir -p "$APP/Contents/Resources"
cp "$ROOT/platform/macos/Resources/ATIV.icns" "$APP/Contents/Resources/ATIV.icns"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>ATIV Reference</string>
<key>CFBundleDisplayName</key><string>ATIV Reference (Internal)</string>
<key>CFBundleIdentifier</key><string>com.tlolabs.ativ.reference</string>
<key>CFBundleExecutable</key><string>ATIV</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$VERSION</string>
<key>CFBundleVersion</key><string>$VERSION</string>
<key>CFBundleIconFile</key><string>ATIV</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
printf 'INTERNAL REFERENCE ONLY — NEVER PUBLISH\n' > "$APP/Contents/Resources/INTERNAL-REFERENCE.txt"
python3 "$ROOT/script/validate_avalonia_reference.py" "$APP"
ditto -c -k --keepParent "$APP" "$OUT/ATIV-Reference-macos-arm64.zip"
printf '%s\n' "$OUT/ATIV-Reference-macos-arm64.zip"
