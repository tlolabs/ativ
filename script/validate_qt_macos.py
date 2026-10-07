#!/usr/bin/env python3
"""Check the experiment has no unresolved or Homebrew-linked Mach-O dependencies."""
from pathlib import Path
import plistlib
import subprocess
import sys

app = Path(sys.argv[1]).resolve()
contents = app / 'Contents'
metadata = plistlib.loads((contents / 'Info.plist').read_bytes())
assert metadata['CFBundleIdentifier'] == 'com.tlolabs.ativ.qt-experiment'
assert metadata['LSMinimumSystemVersion'] == '14.0'
for required in ['MacOS/ATIV Qt', 'MacOS/ativ-engine', 'MacOS/ffmpeg', 'MacOS/ffprobe',
                 'PlugIns/platforms/libqcocoa.dylib', 'PlugIns/styles/libqmacstyle.dylib']:
    assert (contents / required).is_file(), required
count = 0
for binary in contents.rglob('*'):
    if binary.is_symlink() or not binary.is_file():
        continue
    with binary.open('rb') as stream:
        magic = stream.read(4)
    if magic not in (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe'):
        continue
    count += 1
    output = subprocess.check_output(['/usr/bin/otool', '-L', str(binary)], text=True)
    # otool -L lists a dylib's own install ID before its dependencies.
    ids = subprocess.check_output(['/usr/bin/otool', '-D', str(binary)], text=True).splitlines()[1:]
    own_id = ids[0].strip() if ids else None
    for line in output.splitlines()[1:]:
        dependency = line.strip().split(' (')[0]
        if dependency == own_id:
            continue
        if dependency.startswith(('/System/Library/', '/usr/lib/')):
            continue
        roots = {'@rpath/': contents / 'Frameworks', '@loader_path/': binary.parent,
                 '@executable_path/': contents / 'MacOS'}
        for prefix, root in roots.items():
            if dependency.startswith(prefix):
                resolved = (root / dependency[len(prefix):]).resolve()
                assert resolved.is_relative_to(contents), (binary, dependency, 'escapes bundle')
                assert resolved.is_file(), (binary, dependency, 'missing dependency')
                break
        else:
            raise AssertionError((binary, dependency, 'external dependency'))
subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)], check=True)
print(f'Qt bundle verified: {count} Mach-O files; all non-system dependencies embedded.')
