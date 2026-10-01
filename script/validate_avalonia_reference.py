#!/usr/bin/env python3
"""Fail closed if an internal Avalonia Mac bundle resembles a production update."""
import plistlib,sys
from pathlib import Path
from validate_package import machine

app=Path(sys.argv[1]); contents=app/'Contents'; binary=contents/'MacOS'
info=plistlib.loads((contents/'Info.plist').read_bytes())
assert info['CFBundleIdentifier']=='com.tlolabs.ativ.reference'
assert info['CFBundleDisplayName']=='ATIV Reference (Internal)'
assert (contents/'Resources/INTERNAL-REFERENCE.txt').is_file()
assert not list(app.rglob('update-config.json'))
assert not list(app.rglob('ativ-update'))
assert not list(app.rglob('Sparkle.framework'))
for name in ('ATIV','ativ-engine','ffmpeg','ffprobe'): machine(binary/name,'macos-arm64')
assert (contents/'Resources/FFmpeg/build.json').is_file()
assert 'packages' not in app.parts
print('Internal Avalonia reference identity and update isolation verified')
