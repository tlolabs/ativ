#!/usr/bin/env python3
"""Compare identified packaged engines with matched Simple exports in a fresh directory.

No build, download, or publication occurs. Validation runs outside timed intervals.
The first observed run is reported separately; OS caches are never claimed cold.
"""
import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def run(command):
    start = time.perf_counter()
    result = subprocess.run([str(x) for x in command], stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=1800)
    seconds = time.perf_counter() - start
    if result.returncode:
        raise RuntimeError(f'{command}: exit {result.returncode}: {result.stdout[-2000:]!r} {result.stderr[-2000:]!r}')
    return seconds, result.stdout.decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='append', required=True, help='label=/absolute/packaged/ativ-engine; repeat per revision')
    for name in ('directory', 'image', 'audio', 'ffmpeg', 'ffprobe', 'reference-video'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--rounds', type=int, default=3)
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error('rounds must be positive')
    engines = {}
    for value in args.engine:
        label, separator, path = value.partition('=')
        if not separator or not label or not label.replace('-', '').isalnum() or label in engines:
            parser.error('engine labels must be unique alphanumeric/hyphen names')
        engines[label] = Path(path).resolve(strict=True)
    root = args.directory.resolve()
    if root.exists():
        parser.error('directory must be new; existing outputs cannot be reused')
    root.mkdir(parents=True)
    image, audio, ffmpeg, ffprobe, reference = [getattr(args, key).resolve(strict=True)
        for key in ('image', 'audio', 'ffmpeg', 'ffprobe', 'reference_video')]
    report = dict(platform=platform.platform(), clock='perf_counter through subprocess completion',
                  cache_policy='first observation separate; no OS cache purge; rotating order',
                  settings=dict(width=1920, height=1080, fps=30, audio_bitrate='128k', render_mode='simple'),
                  inputs={str(p): dict(bytes=p.stat().st_size, sha256=digest(p)) for p in (image, audio, ffmpeg, ffprobe, reference)},
                  engines={label: dict(path=str(p), sha256=digest(p), bytes=p.stat().st_size,
                      build_info=json.loads(run([p, 'build-info'])[1])) for label, p in engines.items()}, runs=[])
    _, raw = run([ffprobe, '-v', 'error', '-show_format', '-of', 'json', audio])
    duration = float(json.loads(raw)['format']['duration'])
    _, control = run([ffmpeg, '-v', 'error', '-i', reference, '-map', '0:v:0', '-f', 'framemd5', '-'])
    control = [line for line in control.splitlines() if not line.startswith('#')]
    assert len(control) == round(duration * 30)
    try:
        for iteration in range(args.rounds + 1):
            labels = list(engines)
            labels = labels[iteration % len(labels):] + labels[:iteration % len(labels)]
            for label in labels:
                output = root / f'{label}-{iteration}.mp4'
                assert not output.exists()
                command = [engines[label], 'render', '--image', image, '--audio', audio, '--output', output,
                           '--width', '1920', '--height', '1080', '--fps', '30', '--audio-bitrate', '128k', '--render-mode', 'simple']
                elapsed, raw = run(command)
                events = [json.loads(line) for line in raw.splitlines()]
                assert {'event': 'stage', 'stage': 'complete'} in events
                timing = next(e for e in events if e['event'] == 'timing')
                assert timing['success'] and timing['render_mode'] == 'simple'
                assert 0 < timing['wall_seconds'] <= elapsed
                row = dict(label=label, iteration=iteration, first_observation=iteration == 0,
                           command=[str(x) for x in command], seconds=elapsed, events=events)
                report['runs'].append(row)
                _, raw = run([ffprobe, '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', output])
                info = json.loads(raw)
                video = next(s for s in info['streams'] if s['codec_type'] == 'video')
                sound = next(s for s in info['streams'] if s['codec_type'] == 'audio')
                assert (video['width'], video['height'], video['avg_frame_rate'], video['codec_name'], video['pix_fmt']) == (1920, 1080, '30/1', 'h264', 'yuv420p')
                assert int(video['nb_read_frames']) == round(duration * 30)
                assert abs(float(video['duration']) - duration) < 0.05
                assert sound['codec_name'] == 'aac' and sound['sample_rate'] == '44100' and sound['channels'] == 1
                assert abs(float(sound['duration']) - duration) < 0.05
                row['probe'] = info
                _, raw = run([ffmpeg, '-v', 'error', '-i', output, '-map', '0:v:0', '-f', 'framemd5', '-'])
                (root / f'{label}-{iteration}.framemd5').write_text(raw)
                assert [line for line in raw.splitlines() if not line.startswith('#')] == control
                row['decoded_frames_and_timestamps_match'] = True
                _, row['decoded_audio_hash'] = run([ffmpeg, '-v', 'error', '-i', output, '-map', '0:a:0', '-f', 'hash', '-hash', 'sha256', '-'])
                row['output_sha256'] = digest(output)
                print(label, iteration, elapsed, 'validated', flush=True)
        audio_hashes = {r['decoded_audio_hash'] for r in report['runs']}
        assert len(audio_hashes) == 1, 'decoded audio differs between revisions'
        report['decoded_audio_identical'] = True
        report['summary'] = {}
        for label in engines:
            values = [r['seconds'] for r in report['runs'] if r['label'] == label and not r['first_observation']]
            report['summary'][label] = dict(n=len(values), median=statistics.median(values), min=min(values), max=max(values), stdev=statistics.stdev(values) if len(values) > 1 else None)
        print(json.dumps(report['summary']), flush=True)
    finally:
        (root / 'results.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
