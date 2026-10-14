#!/usr/bin/env python3
# SPDX-FileCopyrightText: Thomas Lothian
# SPDX-License-Identifier: GPL-3.0-or-later
"""Track locked source dependencies and emit a release CycloneDX 1.6 SBOM."""

import argparse
import datetime
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "docs/dependency-inventory.json"
UUID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# Crates that are only compiled into ativ-update (shipped on Windows and Linux, omitted on macOS prod)
UPDATER_ONLY_CRATES = {
    "ativ-update",
    "tlo-updater",
    "reqwest",
    "tokio",
    "tokio-rustls",
    "hyper",
    "hyper-rustls",
    "hyper-util",
    "rustls",
    "rustls-pki-types",
    "rustls-webpki",
    "webpki-roots",
    "ring",
    "quinn-proto",
}


def normalize_license(license_str):
    if not license_str:
        return ""
    # Normalize slashes into SPDX boolean OR
    clean = re.sub(r"\s*/\s*", " OR ", license_str.strip())
    return clean


def format_cyclonedx_licenses(license_str):
    if not license_str:
        return []
    clean = normalize_license(license_str)
    # If the expression contains boolean operators or parentheses, emit as expression
    if any(op in clean for op in (" OR ", " AND ", " WITH ", "(", ")")):
        return [{"expression": clean}]
    # Descriptive non-SPDX strings
    if " " in clean or clean in ("upstream permissive license",):
        return [{"license": {"name": clean}}]
    # Standard atomic SPDX ID
    return [{"license": {"id": clean}}]


def inventory():
    cargo = tomllib.loads((ROOT / "Cargo.lock").read_text())
    workspace = tomllib.loads((ROOT / "Cargo.toml").read_text())
    ffmpeg = json.loads((ROOT / "runtime/platform-runtimes.json").read_text())
    sample = ffmpeg["targets"]["macos-arm64"]
    prior = json.loads(INVENTORY.read_text()) if INVENTORY.exists() else {}
    license_by_key = {(p["name"], p["version"]): p.get("license") for p in prior.get("lockedRustPackages", [])}
    try:
        metadata = json.loads(subprocess.check_output(
            ["cargo", "metadata", "--format-version", "1", "--locked", "--offline"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True))
        license_by_key.update({(p["name"], p["version"]): p.get("license") for p in metadata["packages"]})
    except (OSError, subprocess.CalledProcessError):
        pass

    packages = []
    for package in cargo["package"]:
        item = {"name": package["name"], "version": package["version"]}
        for field in ("source", "checksum"):
            if field in package:
                item[field] = package[field]
        raw_license = license_by_key.get((package["name"], package["version"]))
        if raw_license:
            item["license"] = normalize_license(raw_license)
        # Identify whether crate is shipped across all platforms or updater-only
        if package["name"] in UPDATER_ONLY_CRATES:
            item["targets"] = ["windows-x64", "windows-arm64", "linux-x64", "linux-arm64"]
            item["scope"] = "required (Windows/Linux only)"
        else:
            item["targets"] = ["all"]
            item["scope"] = "required"
        packages.append(item)
    packages.sort(key=lambda p: (p["name"], p["version"], p.get("source", "")))

    native_inputs = [
        {
            "name": "AVID Core FFmpeg runtime",
            "version": sample["version"] + "-r" + str(sample["recipe"]),
            "license": "GPL-2.0-or-later",
            "source": ffmpeg["repository"],
            "scope": "required",
            "delivery": "shipped",
            "targets": ["all"],
            "description": "Precompiled native FFmpeg and ffprobe binary runtime from AVID Core",
        },
        *({
            "name": "Core runtime " + target,
            "version": record["version"],
            "license": "GPL-2.0-or-later",
            "sha256": record["assets"][f'avid-ffmpeg-{record["version"]}-r{record["recipe"]}-{target}.tar.gz']["sha256"],
            "scope": "required",
            "delivery": "shipped",
            "targets": [target],
            "description": f"AVID Core runtime archive for {target}",
        } for target, record in ffmpeg["targets"].items()),
        {
            "name": "x264",
            "version": "0.164",
            "license": "GPL-2.0-or-later",
            "scope": "required",
            "delivery": "shipped",
            "targets": ["all"],
            "description": "H.264 / AVC video encoding library bundled in Core FFmpeg",
        },
        {
            "name": "x265",
            "version": "3.6",
            "license": "GPL-2.0-or-later",
            "scope": "required",
            "delivery": "shipped",
            "targets": ["all"],
            "description": "HEVC / H.265 video encoding library bundled in Core FFmpeg",
        },
        {
            "name": "LAME",
            "version": "3.100",
            "license": "LGPL-2.0-or-later",
            "scope": "required",
            "delivery": "shipped",
            "targets": ["all"],
            "description": "MP3 audio encoding library bundled in Core FFmpeg",
        },
        {
            "name": "zlib",
            "version": "1.3.1",
            "license": "Zlib",
            "scope": "required",
            "delivery": "shipped",
            "targets": ["all"],
            "description": "Data compression library bundled in Core FFmpeg",
        },
        {
            "name": "Sparkle",
            "version": "2.9.6",
            "license": "MIT",
            "source": "script/prepare_sparkle.sh",
            "scope": "required",
            "delivery": "shipped",
            "targets": ["macos-arm64", "macos-intel"],
            "description": "macOS software update framework",
        },
        {
            "name": "Qt6Core",
            "version": "6.8.2",
            "license": "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "source": "platform/qt/CMakeLists.txt",
            "scope": "required",
            "delivery": "shipped",
            "targets": ["windows-x64", "windows-arm64", "linux-x64", "linux-arm64"],
            "description": "Qt 6 Core non-GUI foundation library",
        },
        {
            "name": "Qt6Gui",
            "version": "6.8.2",
            "license": "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "source": "platform/qt/CMakeLists.txt",
            "scope": "required",
            "delivery": "shipped",
            "targets": ["windows-x64", "windows-arm64", "linux-x64", "linux-arm64"],
            "description": "Qt 6 GUI module and platform abstractions",
        },
        {
            "name": "Qt6Widgets",
            "version": "6.8.2",
            "license": "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "source": "platform/qt/CMakeLists.txt",
            "scope": "required",
            "delivery": "shipped",
            "targets": ["windows-x64", "windows-arm64", "linux-x64", "linux-arm64"],
            "description": "Qt 6 desktop widget UI library",
        },
        {
            "name": "Qt6 Platform Plugin (qwindows)",
            "version": "6.8.2",
            "license": "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "source": "platform/qt/CMakeLists.txt",
            "scope": "required",
            "delivery": "shipped",
            "targets": ["windows-x64", "windows-arm64"],
            "description": "Qt Windows platform integration plugin",
        },
        {
            "name": "Qt6 Platform Plugins (qxcb, qwayland-generic)",
            "version": "6.8.2",
            "license": "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "source": "platform/qt/CMakeLists.txt",
            "scope": "required",
            "delivery": "shipped",
            "targets": ["linux-x64", "linux-arm64"],
            "description": "Qt Linux X11 and Wayland platform integration plugins",
        },
        {
            "name": "Qt6 Image Format Plugins (qjpeg, qico, qsvg)",
            "version": "6.8.2",
            "license": "LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only",
            "source": "platform/qt/CMakeLists.txt",
            "scope": "required",
            "delivery": "shipped",
            "targets": ["windows-x64", "windows-arm64", "linux-x64", "linux-arm64"],
            "description": "Qt image format plugins",
        },
    ]

    build_inputs = [
        line.strip()
        for line in (ROOT / "script/requirements-build.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    return {
        "schema": 1,
        "project": "ATIV",
        "projectVersion": workspace["workspace"]["package"]["version"],
        "source": {"cargo": "Cargo.lock", "ffmpeg": "runtime/platform-runtimes.json"},
        "lockedRustPackages": packages,
        "nativeInputs": native_inputs,
        "buildInputs": build_inputs,
    }


def sbom(data, target=None):
    components = []
    project_ver = data["projectVersion"]

    # Process locked Rust packages
    for package in data["lockedRustPackages"]:
        # Filter for package-specific targets
        if target:
            pkg_targets = package.get("targets", ["all"])
            if "all" not in pkg_targets and target not in pkg_targets:
                continue

        component = {
            "type": "library",
            "name": package["name"],
            "version": package["version"],
            "scope": "required",
            "bom-ref": "cargo:" + package["name"] + ":" + package["version"],
        }
        if package.get("source", "").startswith("registry+"):
            component["purl"] = "pkg:cargo/" + package["name"] + "@" + package["version"]
        if package.get("checksum"):
            component["hashes"] = [{"alg": "SHA-256", "content": package["checksum"]}]
        licenses = format_cyclonedx_licenses(package.get("license"))
        if licenses:
            component["licenses"] = licenses
        components.append(component)

    # Process native inputs
    for package in data["nativeInputs"]:
        if target:
            pkg_targets = package.get("targets", ["all"])
            if "all" not in pkg_targets and target not in pkg_targets:
                continue

        component = {
            "type": "library",
            "name": package["name"],
            "version": package["version"],
            "scope": package.get("scope", "required"),
            "bom-ref": "native:" + package["name"],
        }
        if package.get("sha256"):
            component["hashes"] = [{"alg": "SHA-256", "content": package["sha256"]}]
        licenses = format_cyclonedx_licenses(package.get("license"))
        if licenses:
            component["licenses"] = licenses
        if package.get("description"):
            component["description"] = package["description"]
        components.append(component)

    # Process build-only inputs
    for build_item in data.get("buildInputs", []):
        name_ver = build_item.split("==") if "==" in build_item else [build_item, "unknown"]
        b_name, b_ver = name_ver[0], name_ver[1] if len(name_ver) > 1 else "unknown"
        component = {
            "type": "library",
            "name": b_name,
            "version": b_ver,
            "scope": "excluded",
            "bom-ref": f"build:{b_name}:{b_ver}",
            "description": "Python build-time dependency (not shipped in release)",
        }
        components.append(component)

    tgt = target or "all"
    serial = f"urn:uuid:{uuid.uuid5(UUID_NAMESPACE, f'ativ-{project_ver}-{tgt}')}"
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

    return {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": serial,
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "component": {
                "type": "application",
                "name": "ATIV",
                "version": project_ver,
                "licenses": [{"license": {"id": "GPL-3.0-or-later"}}],
            },
        },
        "components": components,
    }


def validate_cyclonedx_1_6(bom_dict):
    """Structural validator for CycloneDX 1.6 compliance."""
    assert bom_dict.get("bomFormat") == "CycloneDX", "Missing or wrong bomFormat"
    assert bom_dict.get("specVersion") == "1.6", "Missing or wrong specVersion"
    assert isinstance(bom_dict.get("version"), int), "version must be integer"
    assert "metadata" in bom_dict and "component" in bom_dict["metadata"], "Missing metadata.component"
    components = bom_dict.get("components", [])
    assert isinstance(components, list), "components must be a list"

    for comp in components:
        assert "type" in comp, f"Component missing type: {comp.get('name')}"
        assert "name" in comp and comp["name"], "Component missing name"
        assert "version" in comp and comp["version"], f"Component missing version: {comp.get('name')}"
        assert "bom-ref" in comp, f"Component missing bom-ref: {comp.get('name')}"
        for lic_entry in comp.get("licenses", []):
            if "expression" in lic_entry:
                expr = lic_entry["expression"]
                assert expr and isinstance(expr, str), f"Invalid license expression: {expr}"
                assert "/" not in expr, f"License expression must not contain slash '/': {expr}"
            elif "license" in lic_entry:
                lic = lic_entry["license"]
                assert "id" in lic or "name" in lic, f"License object must have id or name: {lic}"
            else:
                raise AssertionError(f"Invalid license element structure: {lic_entry}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify inventory is up to date")
    parser.add_argument("--write", action="store_true", help="Write updated docs/dependency-inventory.json")
    parser.add_argument("--target", help="Optional specific platform target (e.g. macos-arm64, windows-x64)")
    parser.add_argument("--sbom-dir", type=Path, help="Directory to emit CycloneDX SBOM")
    args = parser.parse_args()

    data = inventory()
    output = json.dumps(data, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not INVENTORY.exists() or INVENTORY.read_text() != output:
            raise SystemExit("Dependency inventory is stale; run script/dependency_inventory.py --write")
        print("Dependency inventory is current.")

    if args.write:
        INVENTORY.write_text(output)
        print(f"Updated {INVENTORY}")

    if args.sbom_dir:
        args.sbom_dir.mkdir(parents=True, exist_ok=True)
        bom = sbom(data, target=args.target)
        validate_cyclonedx_1_6(bom)
        target_suffix = f"-{args.target}" if args.target else ""
        path = args.sbom_dir / f"ativ-{data['projectVersion']}{target_suffix}-sbom.cdx.json"
        path.write_text(json.dumps(bom, indent=2, sort_keys=True) + "\n")
        print(f"Wrote validated CycloneDX 1.6 SBOM: {path}")


if __name__ == "__main__":
    main()
