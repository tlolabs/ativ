#!/usr/bin/env python3
"""Publish each verified native CI artifact as soon as its own job completes.

The build workflow retains read-only contents permission. This script runs only
in the dedicated publisher and accepts first-party push runs from main or an
annotated stable tag. Development releases are immutable direct downloads;
they never populate the signed automatic-update feed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import tomllib
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

from publish_verified_artifacts import verify_package

REPO = "tlolabs/ativ"
WORKFLOW = ".github/workflows/native-release.yml"
SHA = re.compile(r"[0-9a-f]{40}\Z")
TARGETS = {
    "macos-arm64": ("macOS arm64", "ATIV-macos-arm64", ".zip",
                    ("Native process integration tests", "Validate packaged application and startup")),
    "macos-intel": ("macOS x86_64", "ATIV-macos-x86_64", ".zip",
                    ("Native process integration tests", "Validate packaged application and startup")),
    "windows-x64": ("Windows x64", "ATIV-windows-x64", ".zip",
                    ("Native integration and extracted portable ZIP smoke tests",)),
    "windows-arm64": ("Windows ARM64", "ATIV-windows-ARM64", ".zip",
                      ("Native integration and extracted portable ZIP smoke tests",)),
    "linux-x64": ("Linux x86_64", "ATIV-linux-x86_64", ".AppImage",
                  ("Native Qt and package smoke tests",)),
    "linux-arm64": ("Linux aarch64", "ATIV-linux-aarch64", ".AppImage",
                    ("Native Qt and package smoke tests",)),
}
EVIDENCE_TARGETS = {
    "macos-arm64": "macos-arm64",
    "macos-intel": "macos-x86_64",
    "windows-x64": "windows-x86_64",
    "windows-arm64": "windows-arm64",
    "linux-x64": "linux-x86_64",
    "linux-arm64": "linux-arm64",
}
COMMON_STEPS = {
    "Configure build identity",
    "Acquire the exact authenticated Core runtime",
    "Verify ATIV tests and packaged media contract",
    "Build and package native application",
    "Record exact native host evidence",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def api(method, path, payload=None, upload=False, missing_ok=False):
    token = os.environ.get("GH_TOKEN")
    require(token, "GH_TOKEN is required")
    base = "https://uploads.github.com" if upload else "https://api.github.com"
    data = payload if isinstance(payload, bytes) else (
        json.dumps(payload).encode() if payload is not None else None
    )
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ativ-native-publisher",
    }
    if data is not None:
        headers["Content-Type"] = "application/octet-stream" if upload else "application/json"
    request = Request(base + "/" + path.lstrip("/"), data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=180) as response:
            body = response.read()
            return json.loads(body) if body else None
    except HTTPError as error:
        if missing_ok and error.code == 404:
            return None
        detail = error.read(1000).decode(errors="replace")
        raise RuntimeError(f"GitHub API HTTP {error.code}: {detail}") from error


def source_version(revision):
    result = subprocess.run(["git", "show", f"{revision}:Cargo.toml"],
                            capture_output=True, text=True, check=True)
    return tomllib.loads(result.stdout)["workspace"]["package"]["version"]


def release_identity(run):
    require(run["repository"]["full_name"] == REPO and
            run["head_repository"]["full_name"] == REPO and
            run["event"] == "push" and run["path"] == WORKFLOW and
            SHA.fullmatch(run["head_sha"]) is not None,
            "Only first-party native push runs may publish")
    base = source_version(run["head_sha"])
    branch = run["head_branch"]
    stable = branch == f"v{base}"
    require(branch == "main" or stable, "Unexpected release source branch or tag")
    version = base if stable else f"{base}-dev.{run['run_number']}"
    tag = branch if stable else f"development-{version}"
    return version, tag, stable


def ensure_tag(tag, revision, stable):
    ref = api("GET", f"repos/{REPO}/git/ref/tags/{tag}", missing_ok=True)
    if ref is None:
        require(not stable, "Stable publication requires an existing annotated tag")
        try:
            ref = api("POST", f"repos/{REPO}/git/refs",
                      {"ref": f"refs/tags/{tag}", "sha": revision})
        except RuntimeError:
            ref = api("GET", f"repos/{REPO}/git/ref/tags/{tag}")
    obj = ref["object"]
    if stable:
        require(obj["type"] == "tag", "Stable tag must be annotated")
        obj = api("GET", f"repos/{REPO}/git/tags/{obj['sha']}")["object"]
    require(obj["type"] == "commit" and obj["sha"] == revision,
            "Release tag does not identify the verified source revision")


def native_job(jobs, target):
    name, _, _, platform_steps = TARGETS[target]
    matches = [job for job in jobs if job["name"] == name]
    require(len(matches) <= 1, f"Duplicate {name} jobs")
    if not matches:
        return None
    job = matches[0]
    if job["status"] != "completed":
        return None
    if job["conclusion"] != "success":
        raise ValueError(f"{name} did not pass: {job['conclusion']}")
    passed = {step["name"] for step in job.get("steps", [])
              if step.get("conclusion") == "success"}
    required = COMMON_STEPS | set(platform_steps)
    require(required <= passed and any(
        step.startswith("Run actions/upload-artifact@") for step in passed),
        f"{name} lacks native tests, package checks, host evidence, or artifact upload")
    return job


def candidate_artifact(artifacts, job, target, run):
    expected = TARGETS[target][1]
    matches = [artifact for artifact in artifacts if
               artifact["name"] == expected and
               artifact["workflow_run"]["id"] == run["id"] and
               artifact["workflow_run"]["head_sha"] == run["head_sha"] and
               job["started_at"] <= artifact["created_at"] <= job["completed_at"]]
    require(len(matches) <= 1, f"Duplicate candidate artifact for {target}")
    if not matches:
        return None
    artifact = matches[0]
    require(not artifact["expired"] and
            re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.get("digest") or "") is not None,
            f"Candidate artifact for {target} has no verifiable digest")
    return artifact


def read_candidate(artifact, run, target, version, directory):
    archive = directory / "candidate.zip"
    with archive.open("wb") as stream:
        subprocess.run(["gh", "api",
                        f"repos/{REPO}/actions/artifacts/{artifact['id']}/zip"],
                       stdout=stream, check=True)
    require(sha256(archive) == artifact["digest"].removeprefix("sha256:"),
            "Actions artifact archive digest mismatch")
    package_name = f"ATIV-{version}-{target}{TARGETS[target][2]}"
    evidence_target = EVIDENCE_TARGETS[target]
    evidence_name = f"host-{evidence_target}.json"
    with zipfile.ZipFile(archive) as zipped:
        names = {item.filename for item in zipped.infolist() if not item.is_dir()}
        require(names == {package_name, evidence_name},
                f"Unexpected candidate files: {sorted(names)}")
        for name in names:
            item = zipped.getinfo(name)
            require(item.file_size > 0 and item.file_size < 1024 * 1024 * 1024 and
                    ((item.external_attr >> 16) & 0o170000) != 0o120000,
                    "Invalid candidate file type or size")
            with zipped.open(item) as source, (directory / name).open("wb") as dest:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    dest.write(block)
    package = directory / package_name
    evidence = directory / evidence_name
    require(verify_package(package, version) == target, "Package target mismatch")
    report = json.loads(evidence.read_text())
    require(report["schema"] == 1 and report["scope"] == "native_host_packaging" and
            report["status"] == "passed" and report["application_repository"] == REPO and
            report["application_revision"] == run["head_sha"] and
            report["application_version"] == version and
            report["target"] == evidence_target and
            report["native_target"] == evidence_target,
            "Host evidence identity mismatch")
    origin = report["evidence_origin"]
    require(origin["repository"] == REPO and origin["revision"] == run["head_sha"] and
            origin["event"] == "push" and str(origin["run_id"]) == str(run["id"]),
            "Host evidence does not belong to the source run")
    require(all(report["checks"][check]["status"] == "passed"
                for check in ("packaging", "launch", "media", "lifecycle")),
            "Native functional verification is incomplete")
    packages = [item for item in report["packages"] if item["filename"] == package_name]
    require(len(packages) == 1 and packages[0]["sha256"] == sha256(package) and
            packages[0]["size"] == package.stat().st_size,
            "Host evidence does not match package bytes")
    checksum = directory / f"{package_name}.sha256"
    checksum.write_text(f"{sha256(package)}  {package_name}\n")
    return package, evidence, checksum


def verify_attestation(package, run, tag):
    subprocess.run(
        ["gh", "attestation", "verify", str(package), "--repo", REPO,
         "--signer-workflow", f"{REPO}/{WORKFLOW}",
         "--source-digest", run["head_sha"], "--source-ref", f"refs/tags/{tag}",
         "--deny-self-hosted-runners"], check=True)


def find_release(tag):
    release = api("GET", f"repos/{REPO}/releases/tags/{tag}", missing_ok=True)
    if release:
        return release
    page = 1
    while True:
        releases = api("GET", f"repos/{REPO}/releases?per_page=100&page={page}")
        matches = [item for item in releases if item["tag_name"] == tag]
        require(len(matches) <= 1, "Duplicate releases for tag")
        if matches:
            return api("GET", f"repos/{REPO}/releases/{matches[0]['id']}")
        if len(releases) < 100:
            return None
        page += 1


def release_for(run, tag, version, stable):
    title = f"ATIV {version}" + ("" if stable else " · verified development downloads")
    body = (f"Verified native application downloads from {WORKFLOW} run "
            f"https://github.com/{REPO}/actions/runs/{run['id']}\n"
            f"Source revision: {run['head_sha']}\n\n"
            "Each listed platform passed its native build, package, launch, media, "
            "and host evidence checks. Targets appear as their verification finishes. "
            "macOS bundles use ad-hoc signatures without notarization; Windows and "
            "Linux direct downloads are unsigned. The host evidence assets record "
            "exact package hashes. This release does not add unsigned assets to "
            "an authenticated update feed.\n")
    release = find_release(tag)
    if release is None:
        try:
            release = api("POST", f"repos/{REPO}/releases", {
                "tag_name": tag, "target_commitish": run["head_sha"],
                "name": title, "body": body, "draft": True,
                "prerelease": not stable, "make_latest": "false"})
        except RuntimeError:
            release = find_release(tag)
            if release is None:
                raise
    require(release["tag_name"] == tag and release["name"] == title and
            release["body"].rstrip() == body.rstrip() and
            release["prerelease"] is (not stable),
            "Existing release metadata conflicts with verified source")
    return release


def verified_asset(asset, path):
    require(asset["name"] == path.name and asset["state"] == "uploaded" and
            asset["size"] == path.stat().st_size and
            asset.get("digest") == "sha256:" + sha256(path),
            f"Release asset differs from verified bytes: {path.name}")


def publish_target(run, target, artifact, version, tag, stable):
    with tempfile.TemporaryDirectory(prefix="ativ-platform-publish-") as temporary:
        directory = Path(temporary)
        package, evidence, checksum = read_candidate(
            artifact, run, target, version, directory)
        if stable:
            verify_attestation(package, run, tag)
        ensure_tag(tag, run["head_sha"], stable)
        release = release_for(run, tag, version, stable)
        for path in (evidence, checksum, package):
            release = api("GET", f"repos/{REPO}/releases/{release['id']}")
            matches = [asset for asset in release["assets"] if asset["name"] == path.name]
            require(len(matches) <= 1, "Duplicate release asset name")
            if matches:
                verified_asset(matches[0], path)
                continue
            try:
                asset = api(
                    "POST",
                    f"repos/{REPO}/releases/{release['id']}/assets?name={quote(path.name, safe='')}",
                    path.read_bytes(), upload=True)
            except RuntimeError:
                release = api("GET", f"repos/{REPO}/releases/{release['id']}")
                matches = [item for item in release["assets"] if item["name"] == path.name]
                if len(matches) != 1:
                    raise
                asset = matches[0]
            verified_asset(asset, path)
        release = api("GET", f"repos/{REPO}/releases/{release['id']}")
        for path in (evidence, checksum, package):
            matches = [asset for asset in release["assets"] if asset["name"] == path.name]
            require(len(matches) == 1, "Platform release asset missing")
            verified_asset(matches[0], path)
        if release["draft"]:
            release = api("PATCH", f"repos/{REPO}/releases/{release['id']}",
                          {"draft": False, "make_latest": "true" if stable else "false"})
        require(not release["draft"], "Platform release is still a draft")
        with tempfile.TemporaryDirectory(prefix="ativ-download-check-") as download:
            subprocess.run(["gh", "release", "download", tag, "--repo", REPO,
                            "--pattern", package.name, "--dir", download], check=True)
            require(sha256(Path(download) / package.name) == sha256(package),
                    "Published package download differs from verified bytes")
        print(f"Published {target}: {release['html_url']} ({package.name})", flush=True)


def run_publisher(run_id, wait_minutes):
    run = api("GET", f"repos/{REPO}/actions/runs/{run_id}")
    require(run["id"] == run_id, "Unexpected source run ID")
    version, tag, stable = release_identity(run)
    pending = set(TARGETS)
    failures = {}
    deadline = time.monotonic() + wait_minutes * 60
    completed_seen = None
    while pending:
        run = api("GET", f"repos/{REPO}/actions/runs/{run_id}")
        if run["status"] == "completed" and completed_seen is None:
            completed_seen = time.monotonic()
        jobs = api("GET", f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=100")["jobs"]
        artifacts = api("GET", f"repos/{REPO}/actions/runs/{run_id}/artifacts?per_page=100")["artifacts"]
        for target in list(pending):
            try:
                job = native_job(jobs, target)
                if job is None:
                    if completed_seen is not None and time.monotonic() - completed_seen >= 120:
                        raise ValueError("Native target job did not complete successfully")
                    continue
                artifact = candidate_artifact(artifacts, job, target, run)
                if artifact is None:
                    if completed_seen is not None and time.monotonic() - completed_seen >= 120:
                        raise ValueError("Verified candidate artifact is missing")
                    continue
                publish_target(run, target, artifact, version, tag, stable)
                pending.remove(target)
            except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
                failures[target] = str(error)
                pending.remove(target)
        if not pending:
            break
        if time.monotonic() >= deadline:
            for target in pending:
                failures[target] = "Native verification or artifact upload is still pending"
            break
        time.sleep(20)
    for target, detail in sorted(failures.items()):
        print(f"Unpublished {target}: {detail}", flush=True)
    require(not failures, "One or more platform artifacts remain unpublished")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--wait-minutes", type=int, default=0)
    args = parser.parse_args()
    run_publisher(args.run_id, args.wait_minutes)
