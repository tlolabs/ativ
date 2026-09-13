#!/usr/bin/env python3
# Copyright (C) 2026 Tom Lothian
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
import argparse
import os
import platform
import sys
from pathlib import Path


def normalized_arch(machine: str) -> str:
    aliases = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    return aliases.get(machine.lower(), machine.lower())


def media_tool_name(target_platform: str, tool_name: str) -> str:
    return f"{tool_name}.exe" if target_platform == "windows" else tool_name


def media_tool_candidates(root: Path, target_platform: str, target_arch: str, tool_name: str) -> list[Path]:
    binary_name = media_tool_name(target_platform, tool_name)
    candidates = [
        root / "ffmpeg" / target_platform / target_arch / binary_name,
        root / "ffmpeg" / target_platform / binary_name,
        root / "ffmpeg" / binary_name,
        root / binary_name,
    ]
    if root.suffix.lower() == ".app":
        candidates.extend(
            root / "Contents" / location / binary_name
            for location in ("Resources", "Frameworks", "MacOS")
        )
    unique = []
    seen = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that the expected bundled FFmpeg binary exists for the target platform."
    )
    parser.add_argument(
        "--platform",
        dest="target_platform",
        default=platform.system().lower(),
        help="Target platform: darwin, windows, or linux (default: current platform)",
    )
    parser.add_argument(
        "--arch",
        dest="target_arch",
        default=normalized_arch(platform.machine()),
        help="Target architecture: x86_64, arm64, etc. (default: current architecture)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="App root to validate (default: script directory)",
    )
    parser.add_argument(
        "--require-bundled-ffmpeg",
        action="store_true",
        help="Fail if the platform-specific bundled binary is missing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidate_sets = {
        tool_name: media_tool_candidates(args.root, args.target_platform, args.target_arch, tool_name)
        for tool_name in ("ffmpeg", "ffprobe")
    }

    print(f"Target platform: {args.target_platform}")
    print(f"Target architecture: {args.target_arch}")
    for tool_name, candidates in candidate_sets.items():
        print(f"Searched bundled {tool_name} paths:")
        for candidate in candidates:
            print(f"  {candidate}")

    found_paths = {
        tool_name: next(
            (path for path in candidates if path.is_file() and os.access(path, os.X_OK)),
            None,
        )
        for tool_name, candidates in candidate_sets.items()
    }
    if all(found_paths.values()):
        for tool_name, path in found_paths.items():
            print(f"Bundled {tool_name}: {path}")
        print("Bundled FFmpeg/ffprobe check: OK")
        return 0

    if args.require_bundled_ffmpeg:
        for tool_name, path in found_paths.items():
            if path is None:
                print(f"Missing bundled media binary: {tool_name}", file=sys.stderr)
        return 1

    print("Bundled FFmpeg/ffprobe check: not complete, but not required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
