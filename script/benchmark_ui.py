#!/usr/bin/env python3
"""Local macOS package/process and matched-engine benchmark for ATIV frontends.

This deliberately labels process appearance separately from visible UI readiness.
It never claims launch is visually complete based on a PID or open(1) returning.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = {
    'swiftui': ('packages/ATIV-0.2.6-macos-arm64.zip', 'ATIV.app', 'ATIV'),
    'qt': ('build/qt-macos/ATIV-Qt-macos-arm64.zip', 'ATIV Qt.app', 'ATIV Qt'),
}
ALL = tuple(ARTIFACTS)


def command(args, *, timeout=60, env=None, check=True):
    return subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout, env=env, check=check)


def sha256(file):
    digest = hashlib.sha256()
    with file.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def tree_bytes(folder):
    total = 0
    for base, _, files in os.walk(folder):
        for name in files:
            file = Path(base) / name
            if not file.is_symlink(): total += file.stat().st_size
    return total


def json_file(file, data):
    file.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + '\n')


def extract(name, destination):
    relative_zip, bundle_name, executable = ARTIFACTS[name]
    archive = ROOT / relative_zip
    if not archive.is_file(): raise FileNotFoundError(archive)
    folder = destination / 'packages' / name
    folder.mkdir(parents=True)
    command(['/usr/bin/ditto', '-x', '-k', archive, folder], timeout=180)
    bundle = folder / bundle_name
    if not bundle.is_dir(): raise RuntimeError(f'{archive}: no {bundle_name}')
    binary = bundle / 'Contents' / 'MacOS'
    for part in (executable, 'ativ-engine', 'ffmpeg', 'ffprobe'):
        if not (binary / part).is_file(): raise RuntimeError(f'{bundle}: missing {part}')
    info = json.loads(command([binary / 'ativ-engine', 'build-info']).stdout)
    files = {part: sha256(binary / part) for part in (executable, 'ativ-engine', 'ffmpeg', 'ffprobe')}
    size = tree_bytes(bundle)
    engine_bytes = (binary / 'ativ-engine').stat().st_size
    media_bytes = sum((binary / x).stat().st_size for x in ('ffmpeg', 'ffprobe'))
    assets_bytes = tree_bytes(bundle / 'Contents' / 'Resources')
    support_bytes = tree_bytes(bundle / 'Contents' / 'Frameworks') + tree_bytes(bundle / 'Contents' / 'PlugIns')
    structure = {'ui_and_support': max(0, size - engine_bytes - media_bytes - assets_bytes - support_bytes),
                 'engine': engine_bytes, 'media_tools': media_bytes,
                 'assets_and_licenses': assets_bytes, 'supporting_frameworks_and_plugins': support_bytes}
    return {'name': name, 'archive': str(archive), 'archive_bytes': archive.stat().st_size,
            'archive_sha256': sha256(archive), 'bundle': str(bundle), 'installed_logical_bytes': size,
            'breakdown_bytes': structure, 'binary_hashes': files, 'engine_identity': info,
            'executable': str(binary / executable), 'engine': str(binary / 'ativ-engine'),
            'ffprobe': str(binary / 'ffprobe')}


def machine():
    def optional(args):
        try: return command(args, timeout=20).stdout.strip()
        except Exception as error: return f'unavailable: {error}'
    return {
        'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'host': platform.platform(), 'machine': platform.machine(),
        'physical_ram_bytes': int(optional(['/usr/sbin/sysctl', '-n', 'hw.memsize']) or 0),
        'chip': optional(['/usr/sbin/sysctl', '-n', 'machdep.cpu.brand_string']),
        'display': optional(['/usr/sbin/system_profiler', 'SPDisplaysDataType']),
        'power': optional(['/usr/bin/pmset', '-g', 'batt']),
        'power_mode': optional(['/usr/bin/pmset', '-g', 'custom']),
        'git_commit': optional(['/usr/bin/git', '-C', str(ROOT), 'rev-parse', 'HEAD']),
        'git_status': optional(['/usr/bin/git', '-C', str(ROOT), 'status', '--short']),
        'qt_version': optional(['/opt/homebrew/bin/qmake6', '-query', 'QT_VERSION']),
        'swift_version': optional(['/usr/bin/env', 'DEVELOPER_DIR=/Library/Developer/CommandLineTools', '/usr/bin/swift', '--version']),
        'dotnet_sdk': optional(['/usr/local/share/dotnet/dotnet', '--version']) if Path('/usr/local/share/dotnet/dotnet').exists() else 'not installed',
        'notes': 'macOS only; OS caches not flushed; apps and background system activity left running. Process idle does not imply a visible ready UI.',
    }


def make_fixtures(folder):
    folder.mkdir(parents=True)
    manifest = {}
    for name, width, height, seconds in [('small', 640, 360, 2), ('typical', 1920, 1080, 10), ('large', 3000, 2000, 60)]:
        art = folder / f'{name}.ppm'
        audio = folder / f'{name}.wav'
        if not art.exists():
            # Constant-time per pixel, fixed across runs, with sharp colored regions.
            with art.open('wb') as out:
                out.write(f'P6\n{width} {height}\n255\n'.encode())
                left = bytes((224, 54, 38)) * (width // 2)
                right = bytes((24, 88, 210)) * (width - width // 2)
                for y in range(height):
                    out.write(left + right if y % 16 < 8 else right + left)
        if not audio.exists():
            with wave.open(str(audio), 'wb') as out:
                out.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
                # A quiet deterministic 440-Hz tone, chunked to bound memory.
                for start in range(0, seconds * 44100, 44100):
                    samples = bytearray()
                    for i in range(start, min(start + 44100, seconds * 44100)):
                        samples += int(9000 * math.sin(2 * math.pi * 440 * i / 44100)).to_bytes(2, 'little', signed=True)
                    out.writeframesraw(samples)
        manifest[name] = {'image': str(art), 'image_sha256': sha256(art), 'audio': str(audio),
                          'audio_sha256': sha256(audio), 'seconds': seconds, 'width': width, 'height': height}
    return manifest


def process_snapshot():
    rows = command(['/bin/ps', '-axo', 'pid=,ppid=,rss=,time=,command='], timeout=10).stdout.splitlines()
    result = {}
    for row in rows:
        fields = row.strip().split(None, 4)
        if len(fields) == 5 and fields[0].isdigit():
            result[int(fields[0])] = {'ppid': int(fields[1]), 'rss_kib': int(fields[2]),
                                      'cpu_time': fields[3], 'command': fields[4]}
    return result


def descendants(rows, root_pid):
    found = {root_pid}
    while True:
        more = {pid for pid, entry in rows.items() if entry['ppid'] in found}
        if more <= found: break
        found |= more
    return found & rows.keys()


def physical_footprint(pid):
    try:
        output = command(['/usr/bin/footprint', '-p', str(pid), '-f', 'bytes', '--noCategories'], timeout=10).stdout
        match = re.search(r'phys_footprint:\s*(\d+)\s*B', output)
        return int(match[1]) if match else None
    except Exception:
        return None


def launch(candidate, profile, timeout=30):
    executable = candidate['executable']
    before = set(process_snapshot())
    profile.mkdir(parents=True, exist_ok=True)
    start = time.monotonic_ns()
    result = command(['/usr/bin/open', '-n', '-F', '-g', '--env', f'HOME={profile}',
                      '--env', f'CFFIXED_USER_HOME={profile}', '-a', candidate['bundle']], timeout=timeout)
    requested = time.monotonic_ns()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rows = process_snapshot()
        matches = [pid for pid, entry in rows.items() if pid not in before and executable in entry['command']]
        if matches:
            return matches[0], {'launch_requested_ns': start, 'open_returned_ns': requested,
                                'process_seen_ns': time.monotonic_ns(), 'open_stderr': result.stderr.strip()}
        time.sleep(0.05)
    raise TimeoutError(f'No new process for {candidate["bundle"]}; open said: {result.stderr}')


def stop_owned(pid, executable):
    rows = process_snapshot()
    if pid not in rows or executable not in rows[pid]['command']: return
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if pid not in process_snapshot(): return
        time.sleep(0.1)
    rows = process_snapshot()
    if pid in rows and executable in rows[pid]['command']:
        os.kill(pid, signal.SIGKILL)


def sample(pid, executable, seconds, interval, destination, label):
    deadline = time.monotonic() + seconds
    output = []
    while True:
        now = time.monotonic_ns()
        rows = process_snapshot()
        if pid not in rows or executable not in rows[pid]['command']: break
        pids = sorted(descendants(rows, pid))
        for child in pids:
            role = 'ui' if child == pid else ('engine' if 'ativ-engine' in rows[child]['command'] else 'media_or_helper')
            output.append({'phase': label, 'timestamp_ns': now, 'pid': child, 'role': role,
                           'rss_bytes': rows[child]['rss_kib'] * 1024,
                           'physical_footprint_bytes': physical_footprint(child),
                           'cpu_time': rows[child]['cpu_time'], 'command': rows[child]['command']})
        if time.monotonic() >= deadline: break
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
    return output


def run_launches(candidates, repeats, directory):
    rows, memory = [], []
    # First launch of each app is a profile warm-up; ordinary samples follow.
    for iteration in range(repeats + 1):
        names = list(candidates)
        names = names[iteration % len(names):] + names[:iteration % len(names)]
        for name in names:
            candidate = candidates[name]
            pid = None
            try:
                pid, marks = launch(candidate, directory / 'profiles' / name)
                time.sleep(0.7)
                memory += sample(pid, candidate['executable'], 0, 1, directory, 'launch')
                rows.append({'candidate': name, 'iteration': iteration, 'warmup': iteration == 0,
                             'order': ','.join(names), 'pid': pid, **marks,
                             'open_return_seconds': (marks['open_returned_ns']-marks['launch_requested_ns'])/1e9,
                             'process_seen_seconds': (marks['process_seen_ns']-marks['launch_requested_ns'])/1e9,
                             'ui_visible_seconds': None, 'ui_interactive_seconds': None,
                             'task_ready_seconds': None})
            finally:
                if pid: stop_owned(pid, candidate['executable'])
    return rows, memory


def run_idle(candidates, seconds, interval, directory):
    output = []
    for index, (name, candidate) in enumerate(candidates.items()):
        pid = None
        try:
            pid, _ = launch(candidate, directory / 'profiles' / name)
            time.sleep(2)  # allow ordinary startup work to settle; retained separately from launch timing
            output += sample(pid, candidate['executable'], seconds, interval, directory, f'{name}:process_idle')
        finally:
            if pid: stop_owned(pid, candidate['executable'])
    return output


def validate_video(ffprobe, file, seconds, width, height):
    info = json.loads(command([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', file], timeout=20).stdout)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    sound = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    assert video['codec_name'] == 'h264' and sound['codec_name'] == 'aac'
    assert (video['width'], video['height']) == (width, height)
    assert video['avg_frame_rate'] == '30/1'
    assert abs(float(info['format']['duration']) - seconds) <= 0.15
    return {'video_codec': video['codec_name'], 'audio_codec': sound['codec_name'],
            'width': video['width'], 'height': video['height'],
            'fps': video['avg_frame_rate'], 'duration_seconds': float(info['format']['duration']),
            'output_bytes': file.stat().st_size, 'output_sha256': sha256(file)}


def run_engine(candidates, fixture, repeats, directory):
    rows = []
    for iteration in range(repeats + 1):
        names = list(candidates)
        names = names[iteration % len(names):] + names[:iteration % len(names)]
        for name in names:
            candidate = candidates[name]
            output = directory / 'exports' / f'{name}-{iteration}.mp4'
            output.parent.mkdir(exist_ok=True)
            args = [candidate['engine'], 'render', '--image', fixture['image'], '--audio', fixture['audio'],
                    '--output', output, '--width', '1920', '--height', '1080', '--fps', '30', '--audio-bitrate', '128k']
            start = time.monotonic_ns()
            result = command(args, timeout=180)
            end = time.monotonic_ns()
            events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
            if not any(e.get('event') == 'stage' and e.get('stage') == 'complete' for e in events):
                raise RuntimeError(f'{name} did not report completion')
            validation = validate_video(candidate['ffprobe'], output, fixture['seconds'], 1920, 1080)
            rows.append({'candidate': name, 'iteration': iteration, 'warmup': iteration == 0,
                         'order': ','.join(names), 'start_ns': start, 'end_ns': end,
                         'wall_seconds': (end-start)/1e9, 'engine_wall_seconds': next((e.get('wall_seconds') for e in events if e.get('event') == 'timing'), None),
                         'progress_events': sum(e.get('event') == 'progress' for e in events), **validation})
    return rows


def write_csv(file, rows):
    if not rows: return
    keys = list(dict.fromkeys(key for row in rows for key in row))
    with file.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, keys); writer.writeheader(); writer.writerows(rows)


def describe(rows, field):
    numbers = [row[field] for row in rows if not row.get('warmup') and row.get(field) is not None]
    if not numbers: return None
    return {'count': len(numbers), 'median': statistics.median(numbers), 'min': min(numbers),
            'max': max(numbers), 'stdev': statistics.stdev(numbers) if len(numbers) >= 2 else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for flag in ('quick', 'standard', 'deep'): mode.add_argument('--'+flag, action='store_true')
    parser.add_argument('--candidate', choices=ALL, action='append', help='Repeat to select candidates; default: all candidates')
    parser.add_argument('--workload', choices=('launch', 'idle', 'engine', 'inventory'), action='append', help='Repeat; default: all')
    parser.add_argument('--launches', type=int, help='Ordinary launches per candidate, plus one profile warm-up')
    parser.add_argument('--engine-repeats', type=int, help='Matched exports per candidate, plus one warm-up')
    parser.add_argument('--idle-seconds', type=float, help='Idle observation per candidate')
    parser.add_argument('--sample-interval', type=float, default=2)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64': parser.error('Requires native arm64 macOS')
    mode_name = 'quick' if args.quick else ('standard' if args.standard else 'deep')
    defaults = {'quick': (3, 2, 8), 'standard': (20, 5, 60), 'deep': (40, 10, 180)}[mode_name]
    launches = defaults[0] if args.launches is None else args.launches
    repeats = defaults[1] if args.engine_repeats is None else args.engine_repeats
    idle = defaults[2] if args.idle_seconds is None else args.idle_seconds
    if launches < 0 or repeats < 0 or idle < 0 or args.sample_interval <= 0: parser.error('Counts and durations must be non-negative; sample interval must be positive')
    output = (args.output or ROOT / 'build' / 'benchmark-results' / dt.datetime.now().strftime('%Y%m%d-%H%M%S')).resolve()
    if output.exists(): parser.error(f'Output already exists: {output}')
    output.mkdir(parents=True)
    names = tuple(dict.fromkeys(args.candidate or ALL))
    workloads = set(args.workload or ('inventory', 'launch', 'idle', 'engine'))
    candidates = {name: extract(name, output) for name in names}
    fixtures = make_fixtures(output / 'fixtures')
    env = machine()
    json_file(output / 'environment.json', env)
    json_file(output / 'packages.json', candidates)
    json_file(output / 'fixtures.json', fixtures)
    config = {'mode': mode_name, 'candidates': names, 'workloads': sorted(workloads),
              'launches_per_candidate': launches, 'engine_repeats_per_candidate': repeats,
              'idle_seconds_per_candidate': idle, 'sample_interval_seconds': args.sample_interval,
              'monotonic_clock': 'time.monotonic_ns; seconds are differences within a run'}
    json_file(output / 'configuration.json', config)
    launches_data, memory = ([], [])
    engine = []
    try:
        if 'launch' in workloads and launches:
            launches_data, launch_memory = run_launches(candidates, launches, output)
            memory += launch_memory
        if 'idle' in workloads and idle:
            memory += run_idle(candidates, idle, args.sample_interval, output)
        if 'engine' in workloads and repeats:
            engine = run_engine(candidates, fixtures['typical'], repeats, output)
    finally:
        write_csv(output / 'launches.csv', launches_data)
        write_csv(output / 'process_samples.csv', memory)
        write_csv(output / 'engine_exports.csv', engine)
    summary = {name: {'compressed_bytes': candidate['archive_bytes'],
                      'installed_logical_bytes': candidate['installed_logical_bytes'],
                      'process_seen_seconds': describe([r for r in launches_data if r['candidate'] == name], 'process_seen_seconds'),
                      'headless_export_seconds': describe([r for r in engine if r['candidate'] == name], 'wall_seconds'),
                      'physical_footprint_idle_bytes': describe([r for r in memory if r['phase'] == f'{name}:process_idle' and r['role'] == 'ui'], 'physical_footprint_bytes'),
                      'rss_idle_bytes': describe([r for r in memory if r['phase'] == f'{name}:process_idle' and r['role'] == 'ui'], 'rss_bytes')}
               for name, candidate in candidates.items()}
    json_file(output / 'summary.json', summary)
    command([sys.executable, ROOT / 'script' / 'benchmark_ui_report.py', output], timeout=20)
    print(output, flush=True)

if __name__ == '__main__':
    main()
