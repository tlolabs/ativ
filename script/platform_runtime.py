#!/usr/bin/env python3
"""Acquire one pinned AVID Core platform release after provider attestation.

This is deliberately separate from the production six-target acquirer. Current
platform releases have no attestation, so they fail before a runtime download.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from core_runtime import digest, obj, require, safe_name, verify_directory

ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / 'runtime/platform-runtimes.json'
LEGACY = ROOT / 'runtime/core-runtime.json'
REPOSITORY = 'tlolabs/avid-core'
TARGETS = {'macos-arm64', 'macos-x86_64', 'windows-arm64', 'windows-x86_64', 'linux-arm64', 'linux-x86_64'}
BUILD_WORKFLOWS = {'.github/workflows/ffmpeg.yml', '.github/workflows/ffmpeg-independent.yml'}


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path]))


def record_for(target, pins=None):
    pins = obj(PINS) if pins is None else pins
    require(target in TARGETS and pins.get('schema') == 1 and pins.get('repository') == REPOSITORY
            and pins.get('authentication') == 'github-attestation', 'Unsupported platform pin')
    record = pins['targets'][target]
    legacy = obj(LEGACY)['targets'][target]
    require(record['version'] == legacy['version'] and record['recipe'] == legacy['recipe']
            and record['spec_sha256'] == legacy['spec_sha256'], 'Unsupported runtime specification')
    tag = f'platform-ffmpeg-{record["version"]}-r{record["recipe"]}-{target}-run{record["build_run"]}'
    require(record['release_tag'] == tag and re.fullmatch('[0-9a-f]{40}', record['release_revision'])
            and re.fullmatch('[0-9a-f]{40}', record['build_revision']), 'Invalid platform release identity')
    base = f'avid-ffmpeg-{record["version"]}-r{record["recipe"]}-{target}'
    names = {base + '.tar.gz', base + '-sources.tar.gz', base + '.tar.gz.sha256',
             'platform-release.json', 'SHA256SUMS'}
    require(set(record['assets']) == names, 'Incomplete or unexpected platform assets')
    for name, asset in record['assets'].items():
        require(safe_name(name).name == name and isinstance(asset['id'], int) and asset['id'] > 0
                and isinstance(asset['size'], int) and asset['size'] > 0
                and re.fullmatch('[0-9a-f]{64}', asset['sha256']), 'Invalid asset pin')
    return record, base


def verify_origin(target, record, get=api):
    """Bind an immutable release to one successful native build job, not a matrix."""
    release = get(f'repos/{REPOSITORY}/releases/tags/{record["release_tag"]}')
    require(release['id'] == record['release_id'] and release['tag_name'] == record['release_tag']
            and release.get('immutable') is True and not release['draft'] and not release['prerelease'],
            'Release is mutable, unpublished, or differs from pin')
    assets = {asset['name']: asset for asset in release['assets']}
    require(len(assets) == len(release['assets']) and set(assets) == set(record['assets']),
            'Unexpected release assets')
    for name, expected in record['assets'].items():
        asset = assets[name]
        require(asset['id'] == expected['id'] and asset['state'] == 'uploaded'
                and asset['size'] == expected['size'] and asset['digest'] == 'sha256:' + expected['sha256'],
                'Release asset differs from pin: ' + name)
    ref = get(f'repos/{REPOSITORY}/git/ref/tags/{record["release_tag"]}')
    require(ref['object']['type'] == 'commit' and ref['object']['sha'] == record['release_revision'],
            'Release tag changed')
    run_id = record['build_run']
    run = get(f'repos/{REPOSITORY}/actions/runs/{run_id}')
    require(run['id'] == run_id and run['run_attempt'] == record['build_attempt']
            and run['head_sha'] == record['build_revision'] and run['head_branch'] == 'main'
            and run['event'] in ('push', 'workflow_dispatch') and run['path'] in BUILD_WORKFLOWS
            and run['repository']['full_name'] == REPOSITORY
            and run['head_repository']['full_name'] == REPOSITORY, 'Untrusted build run')
    jobs = get(f'repos/{REPOSITORY}/actions/runs/{run_id}/jobs?per_page=100')['jobs']
    selected = [job for job in jobs if job['id'] == record['native_job_id']]
    require(len(selected) == 1, 'Pinned native job missing')
    job = selected[0]
    passed = {step['name'] for step in job['steps'] if step['conclusion'] == 'success'}
    native = 'Build and validate native Windows runtime' if target.startswith('windows') else 'Build and validate native Unix runtime'
    require(job['name'].split(' / ')[-1] == f'build ({target})' and job['conclusion'] == 'success'
            and {native, 'Upload validated Core runtime candidate and corresponding source'} <= passed,
            'Target native validation did not pass')
    artifacts = get(f'repos/{REPOSITORY}/actions/runs/{run_id}/artifacts?per_page=100')['artifacts']
    selected = [artifact for artifact in artifacts if artifact['id'] == record['artifact_id']]
    require(len(selected) == 1, 'Pinned build artifact missing')
    artifact = selected[0]
    require(artifact['name'] == f'core-runtime-candidate-{target}' and not artifact['expired']
            and artifact['digest'] == 'sha256:' + record['artifact_zip_sha256']
            and artifact['workflow_run']['id'] == run_id
            and artifact['workflow_run']['head_sha'] == record['build_revision'],
            'Build artifact origin differs from pin')


def download(tag, name, directory):
    subprocess.run(['gh', 'release', 'download', tag, '--repo', REPOSITORY,
                    '--pattern', name, '--dir', str(directory)], check=True)


def checked_asset(record, name, directory):
    path = directory / name
    expected = record['assets'][name]
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == expected['size']
            and digest(path) == expected['sha256'], 'Downloaded asset differs from pin: ' + name)
    return path


def verify_attestation(record, provenance):
    subprocess.run(['gh', 'attestation', 'verify', str(provenance), '--repo', REPOSITORY,
                    '--signer-workflow', REPOSITORY + '/.github/workflows/platform-publisher.yml',
                    '--source-digest', record['release_revision'], '--source-ref', 'refs/heads/main',
                    '--deny-self-hosted-runners'], check=True, stdout=subprocess.DEVNULL)


def verify_provenance(target, record, base, provenance):
    expected = {'schema': 1, 'kind': 'direct-download-platform', 'repository': REPOSITORY,
                'target': target, 'build_run': record['build_run'], 'build_attempt': record['build_attempt'],
                'build_revision': record['build_revision'], 'native_job_id': record['native_job_id'],
                'artifact_id': record['artifact_id'], 'artifact_zip_sha256': record['artifact_zip_sha256'],
                'spec_sha256': record['spec_sha256'], 'runtime_archive': base + '.tar.gz',
                'runtime_sha256': record['assets'][base + '.tar.gz']['sha256'],
                'source_archive': base + '-sources.tar.gz',
                'source_sha256': record['assets'][base + '-sources.tar.gz']['sha256']}
    require(obj(provenance) == expected, 'Platform provenance differs from pin')


def verify_checksums(record, base, directory):
    names = set(record['assets']) - {'SHA256SUMS'}
    entries = {}
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([^/\\]+)', line)
        require(match is not None and match[2] not in entries, 'Invalid platform checksum manifest')
        entries[match[2]] = match[1]
    require(set(entries) == names, 'Platform checksum manifest has missing or extra assets')
    for name in names:
        require(entries[name] == record['assets'][name]['sha256'], 'Platform checksum differs from pin')
    require((directory / (base + '.tar.gz.sha256')).read_text()
            == f'{record["assets"][base + ".tar.gz"]["sha256"]}  {base}.tar.gz\n',
            'Runtime checksum sidecar mismatch')


def acquire(target, destination):
    record, base = record_for(target)
    destination = Path(destination)
    require(not destination.exists(), 'Fresh platform acquisition destination required')
    verify_origin(target, record)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.platform-runtime-', dir=destination.parent))
    try:
        tag = record['release_tag']
        download(tag, 'platform-release.json', staging)
        provenance = checked_asset(record, 'platform-release.json', staging)
        # Provider signature is required before downloading or extracting executable bytes.
        verify_attestation(record, provenance)
        verify_provenance(target, record, base, provenance)
        for name in sorted(set(record['assets']) - {'platform-release.json'}):
            download(tag, name, staging)
            checked_asset(record, name, staging)
        verify_checksums(record, base, staging)
        archive, source = base + '.tar.gz', base + '-sources.tar.gz'
        from core_runtime import extract_runtime
        extract_runtime(staging / archive, staging, base)
        runtime = staging / base
        plan = {'build_revision': record['build_revision'], 'targets': {target: {
            'archive': archive, 'sha256': record['assets'][archive]['sha256'],
            'source_archive': source, 'source_sha256': record['assets'][source]['sha256'],
            'checksums_sha256': digest(runtime / 'SHA256SUMS')}}}
        verify_directory(plan, target, runtime)
        require(obj(runtime / 'SOURCE.json')['sha256'] == digest(staging / source),
                'Corresponding source differs from runtime metadata')
        (staging / 'platform-verification.json').write_text(json.dumps({
            'schema': 1, 'target': target, 'release_tag': tag,
            'release_revision': record['release_revision'], 'runtime_sha256': record['assets'][archive]['sha256'],
            'version': record['version'], 'recipe': record['recipe']}, indent=2) + '\n')
        os.replace(staging, destination)
        return destination / base
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=sorted(TARGETS))
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    print(acquire(args.target, args.destination))
