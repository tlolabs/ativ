#!/usr/bin/env python3
"""Diagnostic process-tree sampling for packaged headless exports.

Runs separately from headline timing because footprint sampling perturbs exports.
"""
import argparse
import json
import subprocess
import time
from pathlib import Path
from benchmark_ui import process_snapshot, descendants, physical_footprint, validate_video, write_csv

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('results', type=Path)
parser.add_argument('--candidate', choices=('swiftui', 'qt'), action='append')
parser.add_argument('--sample-interval', type=float, default=0.15)
args = parser.parse_args()
if args.sample_interval <= 0: parser.error('sample interval must be positive')
folder = args.results.resolve()
packages = json.loads((folder / 'packages.json').read_text())
fixture = json.loads((folder / 'fixtures.json').read_text())['large']
selected = args.candidate or list(packages)
rows, runs = [], []
for name in selected:
    package = packages[name]
    output = folder / 'exports' / f'{name}-resource-diagnostic.mp4'
    output.parent.mkdir(exist_ok=True)
    command = [package['engine'], 'render', '--image', fixture['image'], '--audio', fixture['audio'],
               '--output', str(output), '--width', '1920', '--height', '1080', '--fps', '30', '--audio-bitrate', '128k']
    start = time.monotonic_ns()
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    seen = set()
    while process.poll() is None:
        now = time.monotonic_ns()
        tree = process_snapshot()
        for pid in sorted(descendants(tree, process.pid)):
            entry = tree[pid]
            role = ('engine' if pid == process.pid else
                    'media' if '/ffmpeg' in entry['command'] else
                    'ffprobe' if 'ffprobe' in entry['command'] else 'helper')
            seen.add(role)
            rows.append({'candidate': name, 'timestamp_ns': now, 'pid': pid, 'role': role,
                         'rss_bytes': entry['rss_kib'] * 1024,
                         'physical_footprint_bytes': physical_footprint(pid),
                         'cpu_time': entry['cpu_time'], 'command': entry['command']})
        time.sleep(args.sample_interval)
    stdout, stderr = process.communicate(timeout=10)
    if process.returncode:
        raise RuntimeError(f'{name} export exit {process.returncode}: {stderr[-1000:]}')
    validation = validate_video(package['ffprobe'], output, fixture['seconds'], 1920, 1080)
    runs.append({'candidate': name, 'wall_seconds_with_sampling': (time.monotonic_ns() - start) / 1e9,
                 'sample_interval_seconds': args.sample_interval, 'sampled_roles': sorted(seen), **validation})
    print(name, runs[-1]['sampled_roles'], flush=True)
write_csv(folder / 'engine_process_samples.csv', rows)
(folder / 'engine_resource_runs.json').write_text(json.dumps(runs, indent=2) + '\n')
print(folder / 'engine_process_samples.csv')
