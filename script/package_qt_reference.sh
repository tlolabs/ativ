#!/usr/bin/env bash
# Internal-only Apple Silicon Qt reference build and package.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT/script/build_qt_macos.sh" --build
