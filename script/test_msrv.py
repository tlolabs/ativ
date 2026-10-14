#!/usr/bin/env python3
# SPDX-FileCopyrightText: Thomas Lothian
# SPDX-License-Identifier: GPL-3.0-or-later
"""Nonblocking MSRV (Minimum Supported Rust Version) diagnostic."""

from pathlib import Path
import re
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def get_declared_msrv():
    cargo_toml = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    return cargo_toml.get("workspace", {}).get("package", {}).get("rust-version", "1.88")


def get_rustc_version():
    try:
        out = subprocess.run(["rustc", "--version"], capture_output=True, text=True, check=True).stdout
        match = re.search(r"rustc (\d+)\.(\d+)(?:\.(\d+))?", out)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            patch = int(match.group(3)) if match.group(3) else 0
            return (major, minor, patch), out.strip()
    except Exception as exc:
        print(f"Diagnostic warning: unable to run rustc: {exc}", file=sys.stderr)
        return None, "unavailable"
    return None, "unrecognized"


def parse_version_tuple(ver_str):
    parts = [int(p) for p in ver_str.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def main():
    declared = get_declared_msrv()
    declared_tuple = parse_version_tuple(declared)
    actual_tuple, actual_str = get_rustc_version()

    print(f"Declared workspace MSRV: {declared}")
    print(f"Active compiler: {actual_str}")

    if actual_tuple is not None:
        if actual_tuple < declared_tuple:
            print(
                f"[MSRV DIAGNOSTIC] Warning: active rustc ({actual_tuple}) is older than "
                f"workspace minimum ({declared_tuple}).",
                file=sys.stderr,
            )
        else:
            print(f"[MSRV DIAGNOSTIC] Compiler satisfies declared MSRV ({declared}).")

    # Run nonblocking cargo check to verify locked workspace
    try:
        proc = subprocess.run(
            ["cargo", "check", "--workspace", "--locked"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode == 0:
            print("[MSRV DIAGNOSTIC] Locked workspace cargo check: PASS")
        else:
            print(
                f"[MSRV DIAGNOSTIC] Warning: cargo check exited with code {proc.returncode}:\n{proc.stderr}",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"[MSRV DIAGNOSTIC] Warning: cargo check failed: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
