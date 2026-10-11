#!/usr/bin/env python3
# SPDX-FileCopyrightText: Thomas Lothian
# SPDX-License-Identifier: GPL-3.0-or-later
"""Publish only packages produced by verified native jobs in this tag run."""

import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    "macos-arm64": ".zip",
    "macos-intel": ".zip",
    "windows-x64": ".zip",
    "windows-arm64": ".zip",
    "linux-x64": ".AppImage",
    "linux-arm64": ".AppImage",
}


def command(*args, check=True, capture=False):
    return subprocess.run(
        args, cwd=ROOT, check=check, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_package(path, version):
    match = re.fullmatch(
        rf"ATIV-{re.escape(version)}-(macos-(?:arm64|intel)|windows-(?:x64|arm64)|linux-(?:x64|arm64))(\.zip|\.AppImage)",
        path.name,
    )
    if not match or TARGETS.get(match.group(1)) != match.group(2):
        raise ValueError(f"Unexpected package name: {path.name}")
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Empty or missing package: {path.name}")
    target = match.group(1)
    if target.startswith("linux-"):
        with path.open("rb") as stream:
            header = stream.read(20)
        expected_machine = 183 if target.endswith("arm64") else 62
        if len(header) < 20 or header[:4] != b"\x7fELF" or struct.unpack_from("<H", header, 18)[0] != expected_machine:
            raise ValueError(f"{path.name}: wrong AppImage machine type")
    else:
        with zipfile.ZipFile(path) as archive:
            invalid = archive.testzip()
            if invalid:
                raise ValueError(f"{path.name}: corrupt ZIP member {invalid}")
            names = set(archive.namelist())
            required = (
                {"ATIV.app/Contents/MacOS/ATIV", "ATIV.app/Contents/MacOS/ativ-engine",
                 "ATIV.app/Contents/MacOS/ffmpeg", "ATIV.app/Contents/MacOS/ffprobe"}
                if target.startswith("macos-") else
                {"ATIV.exe", "ativ-engine.exe", "ffmpeg.exe", "ffprobe.exe"}
            )
            if not required.issubset(names):
                raise ValueError(f"{path.name}: missing application or runtime members")
            ui_name = ("ATIV.app/Contents/MacOS/ATIV" if target.startswith("macos-")
                       else "ATIV.exe")
            header = archive.read(ui_name)[:4096]
            if target.startswith("macos-"):
                expected = 0x100000C if target.endswith("arm64") else 0x1000007
                if len(header) < 8 or header[:4] != b"\xcf\xfa\xed\xfe" or struct.unpack_from("<I", header, 4)[0] != expected:
                    raise ValueError(f"{path.name}: wrong Mach-O machine type")
            else:
                if len(header) < 68 or header[:2] != b"MZ":
                    raise ValueError(f"{path.name}: invalid Windows executable")
                offset = struct.unpack_from("<I", header, 60)[0]
                expected = 0xAA64 if target.endswith("arm64") else 0x8664
                if offset + 6 > len(header) or header[offset:offset + 4] != b"PE\0\0" or struct.unpack_from("<H", header, offset + 4)[0] != expected:
                    raise ValueError(f"{path.name}: wrong PE machine type")
    return target


def release_info(tag):
    result = command("gh", "release", "view", tag, "--json", "isDraft,isPrerelease,assets",
                     check=False, capture=True)
    return json.loads(result.stdout) if result.returncode == 0 else None


def remote_matches(tag, path, expected):
    with tempfile.TemporaryDirectory(prefix="ativ-release-") as temporary:
        result = command("gh", "release", "download", tag, "--pattern", path.name,
                         "--dir", temporary, check=False)
        copy = Path(temporary) / path.name
        return result.returncode == 0 and copy.is_file() and digest(copy) == expected


def verify_attestation(path):
    repo = os.environ["GITHUB_REPOSITORY"]
    sha = os.environ.get("ATIV_SOURCE_SHA", os.environ["GITHUB_SHA"])
    ref = os.environ.get("ATIV_SOURCE_REF", os.environ["GITHUB_REF"])
    command(
        "gh", "attestation", "verify", str(path), "--repo", repo,
        "--signer-workflow", f"{repo}/.github/workflows/native-release.yml",
        "--source-digest", sha, "--source-ref", ref, "--deny-self-hosted-runners",
    )


def publish(tag, directory):
    version = tomllib.loads((ROOT / "Cargo.toml").read_text())["workspace"]["package"]["version"]
    if tag != f"v{version}":
        raise ValueError(f"Tag {tag!r} does not match workspace version v{version}")
    if not directory.is_dir():
        print("No verified platform artifacts were uploaded; nothing to publish.")
        return 0
    pattern = re.compile(rf"ATIV-{re.escape(version)}-(?:macos-(?:arm64|intel)|windows-(?:x64|arm64)|linux-(?:x64|arm64))\.(?:zip|AppImage)")
    packages = sorted(path for path in directory.iterdir() if path.is_file() and pattern.fullmatch(path.name))
    if not packages:
        print("No verified platform packages were uploaded; nothing to publish.")
        return 0
    verified = []
    errors = []
    for path in packages:
        try:
            target = verify_package(path, version)
            verify_attestation(path)
            verified.append((path, target, digest(path)))
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            errors.append(f"{path.name}: {error}")
    if not verified:
        raise RuntimeError("No package passed identity, integrity, and provenance verification: " + "; ".join(errors))
    info = release_info(tag)
    if info and info["isPrerelease"]:
        raise ValueError(f"Refusing to add stable packages to prerelease {tag}")
    if info is None:
        command("gh", "release", "create", tag, "--verify-tag", "--draft",
                "--title", tag, "--generate-notes")
        info = release_info(tag)
        if info is None:
            raise RuntimeError(f"Could not read draft release {tag}")
    existing = {asset["name"] for asset in info["assets"]}
    published = []
    for path, target, expected in verified:
        if path.name in existing:
            if remote_matches(tag, path, expected):
                published.append(target)
            else:
                errors.append(f"{path.name}: existing release bytes differ; refusing replacement")
            continue
        result = command("gh", "release", "upload", tag, str(path), check=False)
        if result.returncode or not remote_matches(tag, path, expected):
            errors.append(f"{path.name}: upload or downloaded-byte verification failed")
            continue
        published.append(target)
        print(f"Verified uploaded asset: {path.name} sha256={expected}")
    if published:
        command("gh", "release", "edit", tag, "--draft=false", "--latest=true")
        print("Published verified platforms: " + ", ".join(sorted(set(published))))
    for error in errors:
        print(error, file=sys.stderr)
    if errors or not published:
        raise RuntimeError("One or more platform packages could not be published")
    return 0


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3:
            raise ValueError("Usage: publish_verified_artifacts.py TAG ARTIFACT_DIRECTORY")
        raise SystemExit(publish(sys.argv[1], Path(sys.argv[2])))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Release publication failed: {error}", file=sys.stderr)
        raise SystemExit(1)
