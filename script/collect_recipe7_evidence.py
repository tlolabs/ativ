#!/usr/bin/env python3
"""Archive an exact completed qualification run and authenticate its evidence ZIPs."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile
from qualify_recipe7 import LOCK, ROOT


def gh(endpoint):
    return subprocess.check_output(['gh', 'api', endpoint, '--allow-escape-sequences'])


def collect(run_id, revision, output=None):
    base = f'repos/tlolabs/ativ/actions/runs/{run_id}'
    run = json.loads(gh(base))
    assert run['status'] == 'completed' and run['head_sha'] == revision
    assert run['path'] == '.github/workflows/recipe7-qualification.yml'
    artifacts = json.loads(gh(base + '/artifacts?per_page=100'))['artifacts']
    jobs = json.loads(gh(base + '/jobs?per_page=100'))['jobs']
    output = output or ROOT / 'docs/qualification/ci' / str(run_id)
    output.mkdir(parents=True, exist_ok=False)
    reports = {}
    for target in LOCK['targets']:
        matches = [a for a in artifacts if a['name'] == 'R7-evidence-' + target]
        assert len(matches) == 1 and not matches[0]['expired'], target
        artifact = matches[0]
        data = gh(f'repos/tlolabs/ativ/actions/artifacts/{artifact["id"]}/zip')
        assert 'sha256:' + hashlib.sha256(data).hexdigest() == artifact['digest']
        destination = output / target
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            seen = set()
            for member in archive.infolist():
                path = PurePosixPath(member.filename)
                assert not path.is_absolute() and '..' not in path.parts
                assert '\\' not in member.filename and ':' not in member.filename
                assert member.filename not in seen and not stat.S_ISLNK(member.external_attr >> 16)
                seen.add(member.filename)
                if member.is_dir():
                    continue
                file = destination / member.filename
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(archive.read(member))
        paths = list(destination.rglob(target + '.json'))
        assert len(paths) == 1
        report = json.loads(paths[0].read_text())
        assert report['target'] == target and report['ativ_revision'] == revision
        assert report['core_revision'] == LOCK['core_revision']
        assert report['binary_sha256'] == LOCK['targets'][target]['binary_sha256']
        if report['steps']['packaging']['outcome'] == 'success':
            for package in report['packaged_runtime']:
                signed = package['signed_payload']
                assert signed['original_binary_sha256'] == report['binary_sha256']
                if 'actual_binary_sha256' in package:
                    assert package['actual_binary_sha256'] == signed['signed_binary_sha256']
        reports[target] = {
            'status': report['status'], 'steps': report['steps'],
            'report': str(paths[0].relative_to(output)),
            'evidence_artifact': {key: artifact[key] for key in ['id', 'name', 'digest']},
            'unperformed_gates': report['unperformed_gates'],
        }
    logs = output / 'logs'
    logs.mkdir()
    for job in jobs:
        data = gh(f'repos/tlolabs/ativ/actions/jobs/{job["id"]}/logs')
        (logs / (str(job['id']) + '.log.gz')).write_bytes(gzip.compress(data, mtime=0))
    (output / 'jobs.json').write_text(json.dumps(jobs, indent=2) + '\n')
    (output / 'artifacts.json').write_text(json.dumps(artifacts, indent=2) + '\n')
    summary = {
        'schema': 1, 'status': 'incomplete', 'gate': 'host_packaging',
        'core_revision': LOCK['core_revision'], 'ativ_tested_revision': revision,
        'run_url': run['html_url'], 'run_id': run_id, 'targets': reports,
        'files_sha256': {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(output.rglob('*')) if p.is_file()},
        'production_release_published': False,
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id', type=int)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--output', type=Path, help='Fresh directory; existing evidence is never overwritten')
    args = parser.parse_args()
    collect(args.run_id, args.revision, args.output)
