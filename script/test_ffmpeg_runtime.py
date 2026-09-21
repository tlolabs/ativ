#!/usr/bin/env python3
"""ATIV-owned source-runtime tests: real media, manifest rejection and no PATH fallback."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from ffmpeg_build import ROOT
from ffmpeg_runtime import stage, finish, validate


def test(engine,runtime,target):
    with tempfile.TemporaryDirectory(prefix='ativ-managed-') as temporary:
        staged=Path(temporary)/'bundle';staged.mkdir()
        suffix='.exe' if target.startswith('windows-') else ''
        executable=staged/('ativ-engine'+suffix);shutil.copy2(engine,executable)
        stage(target, runtime, staged)
        finish(target, staged, staged)
        validate(target, staged, staged, runtime)
        env=dict(os.environ,PATH=str(runtime)+os.pathsep+os.environ.get('PATH',''))
        # These edits must fail before any media invocation. Provenance cannot merely be present.
        for name, mutate in [
            ('ativ-runtime.json', lambda data: data.replace(b'"architecture": "', b'"architecture": "wrong-')),
            ('build.json', lambda data: data + b' '),
            ('signed-payload.json', lambda data: data.replace(b'"target": "', b'"target": "wrong-')),
        ]:
            path = staged/name
            original = path.read_bytes()
            try:
                path.write_bytes(mutate(original))
                try:
                    validate(target, staged, staged, runtime)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Accepted changed provenance: ' + name)
                result=subprocess.run([str(executable),'check'],env=env,capture_output=True,timeout=60)
                assert result.returncode!=0,(name,'engine accepted changed provenance')
            finally:
                path.write_bytes(original)
        # A usable fallback pair exists on PATH throughout every negative check.
        for name in ['dependency.json','build.json','payload.json','signed-payload.json','ativ-runtime.json','ffmpeg'+suffix,'ffprobe'+suffix]:
            path=staged/name;original=path.read_bytes();mode=path.stat().st_mode
            path.unlink()
            p=subprocess.run([str(executable),'check'],env=env,capture_output=True,timeout=60)
            assert p.returncode!=0,(name,'missing bundle silently fell back to PATH')
            assert json.loads(p.stdout)['event']=='error'
            path.write_bytes(b'damaged')
            path.chmod(mode)
            p=subprocess.run([str(executable),'check'],env=env,capture_output=True,timeout=60)
            assert p.returncode!=0,(name,'damaged bundle silently fell back to PATH')
            path.write_bytes(original);path.chmod(mode)
        print('Managed bundle: real exports/previews, lifecycle and missing/damaged tools passed')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--target',required=True);a=p.parse_args();test(a.engine.resolve(),a.runtime.resolve(),a.target)
