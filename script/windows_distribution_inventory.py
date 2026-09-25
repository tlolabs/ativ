#!/usr/bin/env python3
# SPDX-FileCopyrightText: Thomas Lothian
# SPDX-License-Identifier: GPL-3.0-or-later
"""Inventory published Windows ZIP contents against NuGet package evidence.

Usage: python3 script/windows_distribution_inventory.py ZIP [ZIP ...] --output PATH
The NuGet cache is evidence for origin matching; ambiguous matches remain explicit.
"""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path


def package_metadata(root: Path):
    packages = {}
    for directory in root.iterdir():
        if not directory.is_dir() or not directory.name.startswith(("microsoft.", "system.numerics.tensors")):
            continue
        for version_dir in directory.iterdir():
            nuspecs = list(version_dir.glob("*.nuspec"))
            if not version_dir.is_dir() or not nuspecs:
                continue
            tree = ET.parse(nuspecs[0]).getroot()
            license_node = next((node for node in tree.iter() if node.tag.rsplit("}", 1)[-1] == "license"), None)
            license_url_node = next((node for node in tree.iter() if node.tag.rsplit("}", 1)[-1] == "licenseUrl"), None)
            license_url = license_url_node.text.strip() if license_url_node is not None and license_url_node.text else None
            license_value = license_node.text.strip() if license_node is not None and license_node.text else "Not specified in NuGet metadata"
            if license_url == "https://aka.ms/WinSDKLicenseURL":
                license_value = "Microsoft Windows Software Development Kit (SDK) for Windows 10 Software License Terms"
            if license_node is not None and license_node.get("type") == "file":
                license_file = version_dir / license_value
                if license_file.exists():
                    first = license_file.read_text(errors="replace").splitlines()[0].strip()
                    license_value = first or license_value
            packages[(directory.name, version_dir.name)] = {
                "license": license_value,
                "licenseFile": license_node.text.strip() if license_node is not None and license_node.get("type") == "file" and license_node.text else None,
                "licenseUrl": license_url or (f"https://www.nuget.org/packages/{directory.name}/{version_dir.name}/License" if license_node is not None else None),
                "url": f"https://www.nuget.org/packages/{directory.name}/{version_dir.name}",
                "directory": version_dir,
            }
    return packages


def dep_assets(data):
    target = data["targets"][data["runtimeTarget"]["name"]]
    result = defaultdict(set)
    for package_id, spec in target.items():
        for kind in ("runtime", "native", "runtimeTargets"):
            for relative in spec.get(kind, {}):
                result[Path(relative).name.lower()].add(package_id)
    return result


def cache_candidates(packages, names):
    result = defaultdict(list)
    for (package, version), metadata in packages.items():
        for file in metadata["directory"].rglob("*"):
            if file.is_file() and file.name.lower() in names:
                result[file.name.lower()].append((package, version, file))
    return result


def is_microsoft_binary(name):
    lower = name.lower()
    return lower.endswith((".dll", ".exe", ".winmd", ".pri", ".xbf", ".dat"))


def analyze(path, packages):
    with zipfile.ZipFile(path) as archive:
        deps = json.loads(archive.read("ATIV.deps.json"))
        listed = dep_assets(deps)
        entries = [item for item in archive.infolist() if not item.is_dir() and is_microsoft_binary(item.filename)]
        candidates = cache_candidates(packages, {Path(item.filename).name.lower() for item in entries})
        files = []
        for item in entries:
            name = Path(item.filename).name.lower()
            data = archive.read(item)
            digest = hashlib.sha256(data).hexdigest()
            exact = []
            for package, version, source in candidates[name]:
                if source.stat().st_size == item.file_size and hashlib.sha256(source.read_bytes()).hexdigest() == digest:
                    exact.append((package, version))
            from_deps = sorted(listed[name])
            if name == "ativ.pri":
                origin, evidence = "ATIV generated resource index", "project output"
            elif name in ("ativ.exe", "ativ.dll", "ativ-engine.exe", "ativ-update.exe", "ffmpeg.exe", "ffprobe.exe"):
                origin, evidence = "ATIV or separately noticed FFmpeg", "project package"
            elif exact:
                origin, evidence = sorted(set(exact)), "byte-identical NuGet cache file"
            elif from_deps:
                origin, evidence = from_deps, "ATIV.deps.json runtime asset"
            else:
                named = sorted({(package, version) for package, version, _ in candidates[name]})
                origin, evidence = named, "filename match only" if named else "unresolved"
            package_licenses = []
            if isinstance(origin, list):
                for package in origin:
                    if isinstance(package, str):
                        identifier, _, version = package.rpartition("/")
                    else:
                        identifier, version = package
                    info = packages.get((identifier.lower(), version.lower()))
                    if info:
                        package_licenses.append({"package": f"{identifier}/{version}", "license": info["license"], "licenseFile": info["licenseFile"], "licenseUrl": info["licenseUrl"], "url": info["url"]})
                    elif identifier.lower() == "runtimepack.microsoft.netcore.app.runtime.win-x64" and version == "8.0.30":
                        package_licenses.append({"package": f"{identifier}/{version}", "license": "MIT", "url": "https://www.nuget.org/packages/Microsoft.NETCore.App.Runtime.win-x64/8.0.30", "evidence": "Microsoft NuGet package license metadata; exact version absent from local cache"})
                    else:
                        package_licenses.append({"package": f"{identifier}/{version}", "license": "Review exact package version", "url": f"https://www.nuget.org/packages/{identifier}/{version}"})
            files.append({"path": item.filename, "sha256": digest, "bytes": item.file_size, "origin": origin, "evidence": evidence, "packageLicenses": package_licenses})
        return {"archive": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "runtimeTarget": deps["runtimeTarget"]["name"], "packages": sorted(deps["libraries"]), "binaryFiles": files}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--nuget-root", type=Path, default=Path.home() / ".nuget/packages")
    args = parser.parse_args()
    packages = package_metadata(args.nuget_root)
    report = {"schema": 1, "method": "ZIP manifest plus ATIV.deps.json and local NuGet license metadata; ambiguous filename matches are not proof of origin", "archives": [analyze(path, packages) for path in args.archives]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
