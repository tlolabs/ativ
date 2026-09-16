#!/usr/bin/env bash
set -euo pipefail
ARCH="${1:?native architecture}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="$ARCH"; [[ "$ARCH" != x86_64 ]] || LABEL=intel
WORK="$(mktemp -d "${RUNNER_TEMP:-/tmp}/ativ-r7-install.XXXXXX")"
MOUNT="$WORK/volume"
mkdir "$MOUNT"
DMG=("$ROOT"/packages/*.dmg)
hdiutil attach "${DMG[0]}" -readonly -nobrowse -mountpoint "$MOUNT"
trap 'hdiutil detach "$MOUNT" >/dev/null 2>&1 || true' EXIT
ditto "$MOUNT/ATIV Development.app" "$WORK/ATIV Development.app"
hdiutil detach "$MOUNT"
trap - EXIT
APP="$WORK/ATIV Development.app"
codesign --verify --deep --strict "$APP"
python3 "$ROOT/script/qualify_installed.py" "$APP" "macos-$LABEL"
REPORT="$WORK/startup.json"
open -n "$APP" --env "ATIV_SMOKE_REPORT=$REPORT"
for attempt in {1..30}; do [[ ! -s "$REPORT" ]] || break; sleep 1; done
test -s "$REPORT"
cp "$REPORT" "$ROOT/build/qualification-evidence/installed-macos-$ARCH-startup.json"
# Stop only the qualification app whose executable is inside this fresh installation.
python3 - "$APP/Contents/MacOS/ATIV" <<'PY'
import os, signal, subprocess, sys, time
processes=subprocess.check_output(['ps','-axo','pid=,command='],text=True)
for line in processes.splitlines():
    pieces=line.strip().split(None,1)
    if len(pieces)==2 and pieces[1]==sys.argv[1]:
        os.kill(int(pieces[0]), signal.SIGTERM)
PY
