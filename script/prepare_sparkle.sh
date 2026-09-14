#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION=2.9.6
SHA256=52bf9e88cdd972fc0c81501377a880e90d47031bd8ca5462488f843e2609e192
CACHE="$ROOT_DIR/build/sparkle/$VERSION"
mkdir -p "$CACHE"
if [[ ! -f "$CACHE/Sparkle.tar.xz" ]]; then
  curl --fail --location --retry 3 --proto '=https' --proto-redir '=https' "https://github.com/sparkle-project/Sparkle/releases/download/$VERSION/Sparkle-$VERSION.tar.xz" -o "$CACHE/Sparkle.tar.xz"
fi
printf '%s  %s\n' "$SHA256" "$CACHE/Sparkle.tar.xz" | shasum -a 256 --check >&2
if [[ ! -d "$CACHE/Sparkle.framework" ]]; then tar -xJf "$CACHE/Sparkle.tar.xz" -C "$CACHE"; fi
printf '%s\n' "$CACHE/Sparkle.framework"
