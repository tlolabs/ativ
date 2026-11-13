#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION=2.10.1
SHA256=1a856d2a9edb8e628de88121d7be04cf0e2167f8641650b78fca00b14244cf27
CACHE="$ROOT_DIR/build/sparkle/$VERSION"
mkdir -p "$CACHE"
if [[ ! -f "$CACHE/Sparkle.tar.xz" ]]; then
  curl --fail --location --retry 3 --proto '=https' --proto-redir '=https' "https://github.com/sparkle-project/Sparkle/releases/download/$VERSION/Sparkle-$VERSION.tar.xz" -o "$CACHE/Sparkle.tar.xz"
fi
printf '%s  %s\n' "$SHA256" "$CACHE/Sparkle.tar.xz" | shasum -a 256 --check >&2
if [[ ! -d "$CACHE/Sparkle.framework" ]]; then tar -xJf "$CACHE/Sparkle.tar.xz" -C "$CACHE"; fi
printf '%s\n' "$CACHE/Sparkle.framework"
