#!/usr/bin/env python3
"""Publish qualified direct downloads only; never mutate tags, releases or feeds."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from release_eligibility import release_reason, STABLE_TAG


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(tag, target):
    if not re.fullmatch(STABLE_TAG, tag):
        raise ValueError('Invalid stable tag')
    if target not in ('linux-x64', 'linux-arm64', 'windows-x64', 'windows-arm64'):
        raise ValueError('Invalid target')
    return f'ATIV-{tag[1:]}-{target}' + ('-unsigned.zip' if target.startswith('windows') else '.AppImage')


def stage(directory, packages, tag, sha, target):
    name = identity(tag, target)
    source = packages / (name.replace('-unsigned.zip', '.zip') if target.startswith('windows') else name)
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or not source.is_file() or source.is_symlink():
        raise ValueError('Missing exact qualified package or invalid source SHA')
    directory.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source, directory / name)
    value = digest(directory / name)
    (directory / (name + '.sha256')).write_text(f'{value}  {name}\n')
    (directory / 'qualification.json').write_text(json.dumps(dict(tag=tag, sha=sha, target=target, name=name, sha256=value, signing='unsigned' if target.startswith('windows') else 'not-applicable')))


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True)


def publication_release(repo, tag, sha):
    # Repeat before EACH upload/idempotent verification: holds, removed Mac
    # prerequisites and moved tags must stop later writes, including a sidecar.
    if json.loads(gh('api', f'repos/{repo}/commits/{tag}'))['sha'] != sha:
        raise ValueError('Remote tag moved')
    release = json.loads(gh('api', f'repos/{repo}/releases/tags/{tag}'))
    hold = os.environ.get('ATIV_WEEKLY_RELEASE_HOLD', '')
    reason = release_reason(release, tag, [], hold)
    if reason != 'missing_qualified_macos_asset':
        raise ValueError('Expected eligible published stable release: ' + str(reason))
    identifier = release.get('id')
    if type(identifier) is not int or identifier <= 0:
        raise ValueError('Invalid release identity')
    assets, previous = [], None
    for page in range(1, 1001):
        rows = json.loads(gh('api', f'repos/{repo}/releases/{identifier}/assets?per_page=100&page={page}'))
        if not isinstance(rows, list) or len(rows) > 100:
            raise ValueError('Invalid release asset page')
        fingerprint = json.dumps(rows, sort_keys=True)
        if rows and fingerprint == previous:
            raise ValueError('Repeated release asset page')
        previous = fingerprint
        assets.extend(rows)
        if len(rows) < 100:
            break
    else:
        raise ValueError('Release asset enumeration exceeded safety limit')
    reason = release_reason(release, tag, assets, hold)
    if reason:
        raise ValueError('Release is not eligible for publication: ' + reason)
    if json.loads(gh('api', f'repos/{repo}/commits/{tag}'))['sha'] != sha:
        raise ValueError('Remote tag moved during eligibility checks')
    return assets


def publish(directory, tag, sha, target):
    name = identity(tag, target)
    meta = json.loads((directory / 'qualification.json').read_text())
    expected = dict(tag=tag, sha=sha, target=target, name=name, sha256=digest(directory / name), signing='unsigned' if target.startswith('windows') else 'not-applicable')
    if meta != expected or not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Qualification identity or checksum mismatch')
    if (directory / (name + '.sha256')).read_text() != f'{meta["sha256"]}  {name}\n':
        raise ValueError('Checksum sidecar mismatch')
    repo = os.environ['GITHUB_REPOSITORY']
    for asset_name in (name, name + '.sha256'):
        assets = publication_release(repo, tag, sha)
        path = directory / asset_name
        existing = next((a for a in assets if a['name'] == asset_name), None)
        if existing:
            with tempfile.TemporaryDirectory() as temporary:
                gh('release', 'download', tag, '--repo', repo, '--pattern', asset_name, '--dir', temporary)
                if digest(Path(temporary) / asset_name) != digest(path):
                    raise ValueError('Refusing to overwrite different existing asset: ' + asset_name)
        else:
            gh('release', 'upload', tag, str(path), '--repo', repo)  # deliberately no --clobber
        with tempfile.TemporaryDirectory() as temporary:
            gh('release', 'download', tag, '--repo', repo, '--pattern', asset_name, '--dir', temporary)
            if digest(Path(temporary) / asset_name) != digest(path):
                raise ValueError('Published asset integrity mismatch')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['stage', 'publish'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--packages', type=Path, default=Path('packages'))
    for key in ('tag', 'sha', 'target'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    if args.mode == 'stage':
        stage(args.directory, args.packages, args.tag, args.sha, args.target)
    else:
        publish(args.directory, args.tag, args.sha, args.target)
