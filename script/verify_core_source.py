#!/usr/bin/env python3
# SPDX-FileCopyrightText: Thomas Lothian
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify the frozen local Core source and its checked-in Cargo integration.

Requires only Python 3.11+. This checks source identity, not upstream publication,
runtime authentication, or application release qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = 'https://github.com/tlolabs/avid-core.git'
REVISION = '8e27a86ec106028d93130de35a35c0eeda7a9ce3'
VERSION = '0.3.3'
SNAPSHOT_SHA256 = '028cdd71f6a9ff716766b3ca677bf6f4e62c340aa9f6043041de691cf5e67e14'


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular_tree(directory):
    """Enumerate without following links, including links to directories."""
    require(directory.is_dir() and not directory.is_symlink(), 'Core source directory is missing or linked')
    files = set()
    for current, directories, names in os.walk(directory):
        for name in directories + names:
            path = Path(current) / name
            require(not path.is_symlink(), 'Linked Core source entry: ' + str(path.relative_to(directory)))
            require(path.is_dir() or path.is_file(), 'Nonregular Core source entry')
        files.update((Path(current) / name).relative_to(directory).as_posix() for name in names)
    return files


def verify(root=ROOT):
    root = Path(root)
    vendor = root / 'vendor/avid-core'
    manifest = read_json(vendor / 'source-manifest.json')
    require(manifest['repository'] == REPOSITORY and manifest['revision'] == REVISION
            and manifest['version'] == VERSION and manifest['local_tag'] == 'v' + VERSION,
            'Core source manifest identity differs from the approved local snapshot')
    require(manifest['crate_directory'] == 'avid-core-' + VERSION, 'Unexpected Core crate directory')
    expected = manifest['files_sha256']
    require(isinstance(expected, dict) and expected, 'Empty or invalid Core source file manifest')
    for name, checksum in expected.items():
        path = PurePosixPath(name)
        require(name and str(path) == name and not path.is_absolute() and '\\' not in name
                and ':' not in name and all(part not in ('', '.', '..') for part in name.split('/'))
                and name != '.cargo-checksum.json', 'Unsafe Core source manifest path')
        require(isinstance(checksum, str) and re.fullmatch('[0-9a-f]{64}', checksum),
                'Invalid Core source checksum')
    snapshot = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    require(snapshot == manifest['snapshot_sha256'] == SNAPSHOT_SHA256, 'Core snapshot hash mismatch')

    crate = vendor / manifest['crate_directory']
    actual = regular_tree(crate)
    require(actual == set(expected) | {'.cargo-checksum.json'},
            'Core source file set mismatch; missing=' + repr(sorted(set(expected) - actual))
            + ', extra=' + repr(sorted(actual - set(expected) - {'.cargo-checksum.json'})))
    for name, checksum in expected.items():
        require(digest(crate / name) == checksum, 'Core source checksum mismatch: ' + name)
    checksums = read_json(crate / '.cargo-checksum.json')
    require(checksums == {'files': expected, 'package': None}, 'Cargo Core checksum manifest mismatch')
    package = tomllib.loads((crate / 'Cargo.toml').read_text())['package']
    require(package['name'] == 'avid-core' and package['version'] == VERSION, 'Core crate identity mismatch')

    workspace = tomllib.loads((root / 'Cargo.toml').read_text())
    dependency = workspace['workspace']['dependencies']['avid-core']
    require(dependency == {'git': REPOSITORY, 'rev': REVISION, 'version': '=' + VERSION},
            'Workspace Core source pin mismatch')
    lock = tomllib.loads((root / 'Cargo.lock').read_text())
    packages = [entry for entry in lock['package'] if entry['name'] == 'avid-core']
    source = f'git+{REPOSITORY}?rev={REVISION}#{REVISION}'
    require(len(packages) == 1 and packages[0]['version'] == VERSION and packages[0]['source'] == source,
            'Locked Core source identity mismatch')

    require(not (root / '.cargo/config').exists(), 'Ambiguous legacy Cargo configuration')
    config = tomllib.loads((root / '.cargo/config.toml').read_text())
    sources = config['source']
    matching = [entry for entry in sources.values() if entry.get('git') == REPOSITORY]
    require(matching == [{'git': REPOSITORY, 'rev': REVISION, 'replace-with': 'vendored-avid-core'}],
            'Cargo Core source replacement identity mismatch')
    require(sources.get('vendored-avid-core') == {'directory': 'vendor/avid-core'},
            'Cargo Core source replacement directory mismatch')
    require(not config.get('paths'), 'Cargo path overrides bypass the approved source')
    for document in (workspace, config):
        require(not any('avid-core' in entries for entries in document.get('patch', {}).values()),
                'Cargo patch overrides bypass the approved Core source')
        require(not any(key.split(':')[0] == 'avid-core' for key in document.get('replace', {})),
                'Cargo package replacement bypasses the approved Core source')
    return {'version': VERSION, 'revision': REVISION, 'snapshot_sha256': snapshot,
            'files_verified': len(expected), 'source': source}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT, help='ATIV checkout to verify')
    options = parser.parse_args()
    try:
        print(json.dumps(verify(options.root), sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, 'Core source verification failed: ' + str(error) + '\n')
