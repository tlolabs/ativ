#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-$(python3 -c 'import platform; s=platform.system().lower(); print(("macos" if s=="darwin" else "windows" if s.startswith(("windows","mingw","msys")) else s)+"-"+platform.machine().lower())')}"
RUNTIME="$(python3 "$ROOT_DIR/script/core_runtime.py" provision "$TARGET")"
cargo build --manifest-path "$ROOT_DIR/Cargo.toml" --locked -p ativ-engine
ENGINE="$ROOT_DIR/target/debug/ativ-engine"
[[ "$TARGET" != windows-* ]] || ENGINE="$ENGINE.exe"
python3 "$ROOT_DIR/script/test_core_runtime.py" --engine "$ENGINE" --runtime "$RUNTIME" --target "$(python3 -c 'import sys;sys.path.insert(0,sys.argv[1]);from core_runtime import target_id;print(target_id(sys.argv[2]))' "$ROOT_DIR/script" "$TARGET")"
