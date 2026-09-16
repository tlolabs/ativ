#!/usr/bin/env python3
"""Explicit, digest-pinned prepublication acquisition; never a release fallback."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import zipfile
from acquire_core_runtime import ROOT, check_core

LOCK = json.loads((ROOT / 'runtime/recipe7-candidate.json').read_text())


def require(ok, message):
    if not ok:
        raise ValueError(message)


def enabled():
    value = os.environ.get('ATIV_QUALIFICATION_R7')
    if value is None:
        return False
    require(value == '1', 'Invalid qualification opt-in')
    require(os.environ.get('ATIV_CHANNEL') == 'development' and
            os.environ.get('ATIV_RELEASE') != '1' and
            not os.environ.get('GITHUB_REF', '').startswith('refs/tags/'),
            'Recipe 7 candidates are restricted to non-release development qualification')
    require((ROOT / 'runtime/core-revision').read_text().strip() == LOCK['core_revision'],
            'Qualification source pin mismatch')
    check_core()
    return True


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_directory(directory, target):
    require(enabled(), 'Explicit qualification opt-in required')
    expected = LOCK['targets'][target]
    core = check_core()
    sys.path.insert(0, str(core / 'scripts/ffmpeg'))
    import host
    host.verify(directory, target, True)
    build = json.loads((directory / 'build.json').read_text())
    require(build['core_revision'] == LOCK['core_revision'] and not build['core_worktree_modified'],
            'Candidate source identity mismatch')
    require({name: digest(directory / name) for name in expected['binary_sha256']} == expected['binary_sha256'],
            'Not the exact qualified Recipe 7 executable pair')
    source = json.loads((directory / 'SOURCE.json').read_text())
    require(source['sha256'] == expected['source_sha256'] and
            digest(directory.parent / source['asset']) == expected['source_sha256'],
            'Candidate corresponding-source mismatch')


def provision(target):
    require(enabled(), 'Explicit qualification opt-in required')
    native_os = {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}[platform.system()]
    arch = {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(platform.machine().lower(), platform.machine().lower())
    require(target == native_os + '-' + arch, 'Qualification requires native target execution')
    expected = LOCK['targets'][target]
    root = ROOT / 'build/recipe7' / target
    core = check_core()
    sys.path.insert(0, str(core / 'scripts/ffmpeg'))
    from build import artifact_name
    from artifact import validate_runtime, validate_sources
    spec = json.loads((core / 'runtime/ffmpeg/spec.json').read_text())
    name = artifact_name(spec, target)
    directory = root / name
    if directory.exists():
        verify_directory(directory, target)
        return directory
    root.mkdir(parents=True, exist_ok=True)
    repo = spec['release_repository']
    def gh(endpoint):
        return subprocess.check_output(['gh', 'api', endpoint])
    run = json.loads(gh(f'repos/{repo}/actions/runs/{LOCK["run_id"]}'))
    require(run['head_sha'] == LOCK['core_revision'] and run['conclusion'] == 'success' and
            run['path'] == '.github/workflows/ffmpeg.yml', 'Unexpected Core candidate run')
    artifact = json.loads(gh(f'repos/{repo}/actions/artifacts/{expected["artifact_id"]}'))
    require(artifact['digest'] == expected['artifact_sha256'] and not artifact['expired'] and
            artifact['workflow_run']['id'] == LOCK['run_id'], 'Unexpected Core Actions artifact')
    data = gh(f'repos/{repo}/actions/artifacts/{expected["artifact_id"]}/zip')
    require('sha256:' + hashlib.sha256(data).hexdigest() == expected['artifact_sha256'], 'Actions ZIP digest mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        seen = set()
        for member in archive.infolist():
            filename = member.filename
            require('/' not in filename and '\\' not in filename and ':' not in filename and
                    filename not in {'.', '..'} and filename not in seen and
                    not stat.S_ISLNK(member.external_attr >> 16), 'Unsafe Actions artifact member')
            seen.add(filename)
            (root / filename).write_bytes(archive.read(member))
    runtime = root / (name + '.tar.gz')
    source = root / (name + '-sources.tar.gz')
    require(digest(runtime) == expected['runtime_sha256'] and digest(source) == expected['source_sha256'],
            'Candidate archive checksum mismatch')
    files = validate_runtime(runtime, spec, target, LOCK['core_revision'], clean=True)
    validate_sources(source, spec, target)
    directory.mkdir()
    for filename, contents in files.items():
        path = directory / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents)
        if filename in expected['binary_sha256']:
            path.chmod(0o755)
    verify_directory(directory, target)
    (root / 'acquisition-evidence.json').write_text(json.dumps({
        'schema': 1, 'qualification_only': True, 'core_revision': LOCK['core_revision'],
        'run_id': LOCK['run_id'], 'target': target, **expected,
    }, indent=2) + '\n')
    return directory


if __name__ == '__main__':
    print(provision(sys.argv[1]))
