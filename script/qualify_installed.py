#!/usr/bin/env python3
"""Validate the installed package and retain its exact runtime identity."""
import json
from pathlib import Path
import sys
from validate_package import validate
from acquire_core_runtime import ROOT

root = Path(sys.argv[1]).resolve()
target = sys.argv[2]
validate(root, target)
if target.startswith('macos'):
    metadata = root / 'Contents/Resources/FFmpeg'
elif target.startswith('windows'):
    metadata = root
else:
    metadata = root / 'usr/lib/ativ-development'
    if not metadata.exists():
        metadata = root / 'usr/lib/ativ'
out = ROOT / 'build/qualification-evidence'
out.mkdir(parents=True, exist_ok=True)
(out / ('installed-' + target + '.json')).write_text(json.dumps({
    'status': 'passed', 'target': target,
    'scope': 'installed package architecture, resources, managed discovery, media/lifecycle and runtime provenance',
    'signed_payload': json.loads((metadata / 'signed-payload.json').read_text()),
    'provenance': json.loads((metadata / 'ativ-runtime.json').read_text()),
}, indent=2) + '\n')
