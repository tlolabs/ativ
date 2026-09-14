#!/usr/bin/env python3
"""Packaging gate for the single approved FFmpeg build; never selects a fallback."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', required=True)
    parser.add_argument('--ffmpeg', required=True)
    parser.add_argument('--ffprobe', required=True)
    options = parser.parse_args()
    engine, ffmpeg, ffprobe = [str(Path(p).resolve()) for p in (options.engine, options.ffmpeg, options.ffprobe)]

    def capture(args):
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=45).stdout

    # The canonical discovery validator owns identity and pair matching.
    event = json.loads(capture([engine, 'check', '--ffmpeg', ffmpeg, '--ffprobe', ffprobe]))
    identifier = event['ffmpeg'].split()[2]
    assert identifier == '9.0.1' or identifier.startswith(('9.0.1-', 'n9.0.1-')), identifier
    required_encoders = {'libx264', 'libx265', 'aac', 'libmp3lame', 'png'}
    if sys.platform == 'darwin':
        required_encoders.add('aac_at')
    encoders = {fields[1] for line in capture([ffmpeg, '-hide_banner', '-encoders']).splitlines()
                if len(fields := line.split()) >= 2 and fields[0][0] in 'VAS' and len(fields[0]) == 6}
    assert required_encoders <= encoders, f'Missing distribution encoders: {required_encoders - encoders}'
    required_filters = {'scale', 'crop', 'split', 'gblur', 'overlay', 'format', 'hflip', 'vflip',
                        'pad', 'trim', 'setpts', 'atrim', 'aformat', 'asetpts', 'concat'}
    filters = {fields[1] for line in capture([ffmpeg, '-hide_banner', '-filters']).splitlines()
               if len(fields := line.split()) >= 3 and '->' in fields[2]}
    assert required_filters <= filters, f'Missing distribution filters: {required_filters - filters}'
    print(f'Approved-version capability gate passed: {identifier}; {", ".join(sorted(required_encoders))}')


if __name__ == '__main__':
    main()
