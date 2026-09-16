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
from pathlib import Path
processes=subprocess.check_output(['ps','-axo','pid=,command='],text=True)
found=False
for line in processes.splitlines():
    pieces=line.strip().split(None,1)
    if len(pieces)==2 and Path(pieces[1]).resolve()==Path(sys.argv[1]).resolve():
        found=True
        pid=int(pieces[0])
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(.1)
        else:
            raise RuntimeError('Installed qualification app did not exit')
if not found:
    raise RuntimeError('Installed qualification app was not running after startup')
PY
