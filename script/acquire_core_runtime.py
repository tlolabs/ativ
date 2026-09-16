#!/usr/bin/env python3
"""ATIV supplies only target/destination to the selected Core revision's acquisition policy."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
CORE=ROOT.parent/'AVID Core'


def check_core():
    expected=(ROOT/'runtime/core-revision').read_text().strip()
    actual=subprocess.check_output(['git','-C',str(CORE),'rev-parse','HEAD'],text=True).strip()
    if actual!=expected:
        raise ValueError('Local Core checkout differs from ATIV’s tested revision')
    return CORE


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('target');p.add_argument('destination',type=Path);a=p.parse_args()
    subprocess.run([sys.executable,str(check_core()/'scripts/ffmpeg/acquire.py'),a.target,str(a.destination)],check=True)
