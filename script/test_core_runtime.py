#!/usr/bin/env python3
"""Host migration tests: isolated candidate bundle, actual media, and no production PATH fallback."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from acquire_core_runtime import ROOT, check_core


def test(engine,runtime,target):
    core=check_core()
    with tempfile.TemporaryDirectory(prefix='ativ-managed-') as temporary:
        staged=Path(temporary)/'bundle';staged.mkdir()
        suffix='.exe' if target.startswith('windows-') else ''
        executable=staged/('ativ-engine'+suffix);shutil.copy2(engine,executable)
        subprocess.run([sys.executable,str(core/'scripts/ffmpeg/host.py'),'stage',target,str(runtime),
                        '--destination',str(staged),'--candidate'],check=True)
        subprocess.run([sys.executable,str(ROOT/'script/test_engine_contract.py'),'--engine',str(executable),
                        '--ffmpeg',str(staged/('ffmpeg'+suffix)),'--ffprobe',str(staged/('ffprobe'+suffix)),'--managed'],check=True)
        # A usable fallback pair exists on PATH throughout every negative check.
        env=dict(os.environ,PATH=str(runtime)+os.pathsep+os.environ.get('PATH',''))
        for name in ['spec.json','build.json','ffmpeg'+suffix,'ffprobe'+suffix]:
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
