#!/usr/bin/env python3
"""Track locked source dependencies and emit a release CycloneDX SBOM."""

import argparse
import json
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "docs/dependency-inventory.json"


def inventory():
    cargo = tomllib.loads((ROOT / "Cargo.lock").read_text())
    workspace = tomllib.loads((ROOT / "Cargo.toml").read_text())
    ffmpeg = json.loads((ROOT / "runtime/ffmpeg/dependency.json").read_text())
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
        if license_by_key.get((package["name"], package["version"])):
            item["license"] = license_by_key[(package["name"], package["version"])]
        packages.append(item)
    packages.sort(key=lambda p: (p["name"], p["version"], p.get("source", "")))
    return {
        "schema": 1,
        "project": "ATIV",
        "projectVersion": workspace["workspace"]["package"]["version"],
        "source": {"cargo": "Cargo.lock", "ffmpeg": "runtime/ffmpeg/dependency.json"},
        "lockedRustPackages": packages,
        "nativeInputs": [
            {"name": "FFmpeg", "version": ffmpeg["source"]["version"], "license": "GPL-2.0-or-later", "sha256": ffmpeg["source"]["sha256"]},
            *({"name": name, "version": spec["version"], "license": spec["license"], "sha256": spec["sha256"]} for name, spec in ffmpeg["external_libraries"].items()),
            {"name": "Sparkle", "version": "2.9.6", "license": "upstream permissive license", "source": "script/prepare_sparkle.sh"},
            {"name": "Microsoft.WindowsAppSDK", "version": "2.4.0", "license": "Microsoft package terms; review required", "source": "platform/windows/ATIV/ATIV.csproj"},
            {"name": "GTK", "version": ">=4.10", "license": "LGPL-family", "source": "platform/linux/meson.build"},
            {"name": "libadwaita", "version": ">=1.4", "license": "LGPL-family", "source": "platform/linux/meson.build"},
            {"name": "json-glib", "version": "system package", "license": "LGPL-family", "source": "platform/linux/meson.build"},
        ],
        "buildInputs": [line.strip() for line in (ROOT / "script/requirements-build.txt").read_text().splitlines() if line.strip() and not line.startswith("#")],
    }


def sbom(data):
    components = []
    for package in data["lockedRustPackages"]:
        component = {"type": "library", "name": package["name"], "version": package["version"], "bom-ref": "cargo:" + package["name"] + ":" + package["version"]}
        if package.get("source", "").startswith("registry+"):
            component["purl"] = "pkg:cargo/" + package["name"] + "@" + package["version"]
        if package.get("checksum"):
            component["hashes"] = [{"alg": "SHA-256", "content": package["checksum"]}]
        if package.get("license"):
            component["licenses"] = [{"expression": package["license"]}]
        components.append(component)
    for package in data["nativeInputs"]:
        component = {"type": "library", "name": package["name"], "version": package["version"], "bom-ref": "native:" + package["name"]}
        if package.get("sha256"):
            component["hashes"] = [{"alg": "SHA-256", "content": package["sha256"]}]
        if package.get("license") and "review" not in package["license"] and "family" not in package["license"] and "upstream" not in package["license"]:
            component["licenses"] = [{"license": {"id": package["license"]}}]
        components.append(component)
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": {"component": {"type": "application", "name": "ATIV", "version": data["projectVersion"]}},
            "components": components}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--sbom-dir", type=Path)
    args = parser.parse_args()
    data = inventory()
    output = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.check and INVENTORY.read_text() != output:
        raise SystemExit("Dependency inventory is stale; run script/dependency_inventory.py --write")
    if args.write:
        INVENTORY.write_text(output)
    if args.sbom_dir:
        args.sbom_dir.mkdir(parents=True, exist_ok=True)
        path = args.sbom_dir / f"ativ-{data['projectVersion']}-sbom.cdx.json"
        path.write_text(json.dumps(sbom(data), indent=2, sort_keys=True) + "\n")
        print(path)


if __name__ == "__main__":
    main()
