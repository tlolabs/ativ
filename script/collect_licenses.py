#!/usr/bin/env python3
# SPDX-FileCopyrightText: Thomas Lothian
# SPDX-License-Identifier: GPL-3.0-or-later
"""Collect locked Rust dependency license texts and Qt LGPL/GPL texts for the build target."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent

p = argparse.ArgumentParser()
p.add_argument('destination', type=Path)
p.add_argument('--target')
a = p.parse_args()

command = ['cargo', 'metadata', '--format-version', '1', '--locked']
if a.target:
    command += ['--filter-platform', a.target]
metadata = json.loads(subprocess.check_output(command))
a.destination.mkdir(parents=True, exist_ok=True)
index = []

for package in metadata['packages']:
    if package['source'] is None:
        continue
    root = Path(package['manifest_path']).parent
    if package['name'] == 'avid-core':
        (a.destination.parent / 'AVID_CORE_LICENSE.txt').write_bytes((root / 'LICENSE').read_bytes())
    folder = a.destination / (package['name'] + '-' + package['version'])
    folder.mkdir(exist_ok=True)
    texts = []
    for source in sorted(root.iterdir()):
        if source.is_file() and source.name.upper().startswith(('LICENSE', 'COPYING', 'COPYRIGHT', 'NOTICE')):
            (folder / source.name).write_bytes(source.read_bytes())
            texts.append(source.name)
    index.append(dict(
        name=package['name'],
        version=package['version'],
        license=package['license'],
        repository=package.get('repository'),
        files=texts,
    ))

# Bundle Qt LGPLv3 and GPLv3 license texts for Windows and Linux targets
qt_dir = ROOT / 'licenses' / 'qt'
if qt_dir.is_dir() and (not a.target or any(p in a.target for p in ('windows', 'linux'))):
    qt_dest = a.destination / 'qt'
    qt_dest.mkdir(exist_ok=True)
    qt_files = []
    for f in sorted(qt_dir.iterdir()):
        if f.is_file():
            (qt_dest / f.name).write_bytes(f.read_bytes())
            qt_files.append(f.name)
            (a.destination.parent / f"QT_{f.name}.txt").write_bytes(f.read_bytes())
    index.append(dict(
        name='Qt 6',
        version='6.8.2',
        license='LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only',
        repository='https://code.qt.io/cgit/qt/qtbase.git',
        files=qt_files,
    ))

(a.destination / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
