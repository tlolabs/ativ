#!/usr/bin/env python3
"""Collect locked Rust dependency license texts for the current build target."""
import argparse,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('destination',type=Path);p.add_argument('--target');a=p.parse_args()
command=['cargo','metadata','--format-version','1','--locked']
if a.target:command+=['--filter-platform',a.target]
metadata=json.loads(subprocess.check_output(command))
a.destination.mkdir(parents=True,exist_ok=True)
index=[]
for package in metadata['packages']:
    if package['source'] is None:continue
    root=Path(package['manifest_path']).parent
    folder=a.destination/(package['name']+'-'+package['version']);folder.mkdir(exist_ok=True)
    texts=[]
    for source in sorted(root.iterdir()):
        if source.is_file() and source.name.upper().startswith(('LICENSE','COPYING','COPYRIGHT','NOTICE')):
            (folder/source.name).write_bytes(source.read_bytes());texts.append(source.name)
    index.append(dict(name=package['name'],version=package['version'],license=package['license'],repository=package.get('repository'),files=texts))
(a.destination/'index.json').write_text(json.dumps(index,indent=2)+'\n')
