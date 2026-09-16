#!/usr/bin/env python3
"""Retain partial results without representing missing release gates as passed."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from qualify_recipe7 import LOCK, ROOT, digest

target = sys.argv[1]
steps = json.loads(os.environ.get('QUALIFICATION_STEPS', '{}'))
root = ROOT / 'build/qualification-evidence'
root.mkdir(parents=True, exist_ok=True)
files = {}
for base in [ROOT / 'packages', ROOT / 'build/recipe7' / target]:
    if base.exists():
        for path in base.rglob('*'):
            if path.is_file():
                files[str(path.relative_to(ROOT))] = digest(path)
packaged = []
for pattern in ['build/package-*/**/signed-payload.json', 'build/windows-*/publish/signed-payload.json', 'build/*.AppDir/**/signed-payload.json']:
    for path in ROOT.glob(pattern):
        signed = json.loads(path.read_text())
        binary = path.parents[2] / 'MacOS' if target.startswith('macos') else path.parent
        packaged.append({'path': str(path.relative_to(ROOT)), 'signed_payload': signed,
                         'actual_binary_sha256': {name: digest(binary / name) for name in signed['signed_binary_sha256']},
                         'provenance': json.loads(path.with_name('ativ-runtime.json').read_text())})
report = {
    'schema': 1, 'gate': 'host_packaging', 'status': 'incomplete', 'host': 'ATIV', 'target': target,
    'core_revision': LOCK['core_revision'], 'core_run': LOCK['run_url'],
    'ativ_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'recipe': LOCK['recipe'], 'binary_sha256': LOCK['targets'][target]['binary_sha256'],
    'candidate': LOCK['targets'][target],
    'native_host': {'platform': platform.platform(), 'machine': platform.machine(), 'system': platform.system()},
    'run_url': 'https://github.com/' + os.environ.get('GITHUB_REPOSITORY', 'tlolabs/ativ') + '/actions/runs/' + os.environ.get('GITHUB_RUN_ID', 'local'),
    'steps': steps, 'artifact_sha256': files, 'packaged_runtime': packaged,
    'unperformed_gates': {
        'authenticated_application_upgrade': 'No isolated authenticated delivery endpoint. Package-signature tests and same-version installer replacement are not end-to-end authenticated application upgrades.',
        'manual_ui_accessibility': 'Not performed; automated native launch tests are recorded separately.'},
    'production_release_published': False,
}
if target.startswith('macos'):
    report['unperformed_gates']['production_signing_notarization'] = 'Owner confirms Developer ID/notarization setup is not completed. Ad-hoc signature observations do not satisfy this gate.'
if target.startswith('windows'):
    report['unperformed_gates']['production_signing'] = 'Owner confirms signing setup is not completed. Unsigned candidate observations do not satisfy this gate.'
(root / (target + '.json')).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'target': target, 'status': report['status'], 'steps': steps}))
