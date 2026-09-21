#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCH="${1:?architecture}"
STAGE="$ROOT_DIR/build/package-linux-$ARCH"
export ATIV_SMOKE_REPORT="${RUNNER_TEMP:-$ROOT_DIR/build}/ativ-gtk-smoke.json"
rm -f "$ATIV_SMOKE_REPORT"
NAME=ativ; [[ "${ATIV_CHANNEL:-stable}" != development ]] || NAME=ativ-development
export ATIV_ENGINE_PATH="$STAGE/usr/lib/$NAME/ativ-engine"
export XDG_DATA_DIRS="$STAGE/usr/share:/usr/share"
xvfb-run -a dbus-run-session -- "$STAGE/usr/bin/$NAME" > "$ROOT_DIR/build/gtk-smoke.log" 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT
for attempt in {1..30}; do [[ ! -s "$ATIV_SMOKE_REPORT" ]] || break; sleep 1; done
if [[ ! -s "$ATIV_SMOKE_REPORT" ]]; then cat "$ROOT_DIR/build/gtk-smoke.log"; exit 1; fi
python3 -c 'import json,os; assert json.load(open(os.environ["ATIV_SMOKE_REPORT"]))["presets"]==27'
for desktop in "$STAGE"/usr/share/applications/*.desktop; do desktop-file-validate "$desktop"; done
for deb in "$ROOT_DIR"/packages/*.deb; do dpkg-deb --info "$deb"; dpkg-deb --contents "$deb" > /dev/null; done
# Verify the distributable AppImage mounts/extracts and launches its own native app.
unset ATIV_ENGINE_PATH
rm -f "$ATIV_SMOKE_REPORT"
APPIMAGE_EXTRACT_AND_RUN=1 xvfb-run -a dbus-run-session -- "$ROOT_DIR"/packages/*.AppImage > "$ROOT_DIR/build/appimage-smoke.log" 2>&1 &
IMAGE_PID=$!
for attempt in {1..30}; do [[ ! -s "$ATIV_SMOKE_REPORT" ]] || break; sleep 1; done
kill "$IMAGE_PID" 2>/dev/null || true
if [[ ! -s "$ATIV_SMOKE_REPORT" ]]; then cat "$ROOT_DIR/build/appimage-smoke.log"; exit 1; fi

# Install the actual deb to exercise the compiled runtime path and desktop identity.
if [[ "${CI:-}" == true ]]; then
  sudo apt-get install --yes "$ROOT_DIR"/packages/*.deb
  env PATH= "/usr/lib/$NAME/ativ-engine" check
  unset XDG_DATA_DIRS ATIV_ENGINE_PATH
  rm -f "$ATIV_SMOKE_REPORT"
  xvfb-run -a dbus-run-session -- "/usr/bin/$NAME" > "$ROOT_DIR/build/deb-smoke.log" 2>&1 &
  INSTALLED_PID=$!
  for attempt in {1..30}; do [[ ! -s "$ATIV_SMOKE_REPORT" ]] || break; sleep 1; done
  kill "$INSTALLED_PID" 2>/dev/null || true
  if [[ ! -s "$ATIV_SMOKE_REPORT" ]]; then cat "$ROOT_DIR/build/deb-smoke.log"; exit 1; fi
  sudo apt-get install --reinstall --yes "$ROOT_DIR"/packages/*.deb
  sudo apt-get remove --yes "$NAME"
  test ! -f "/usr/bin/$NAME"
fi
