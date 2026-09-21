#!/usr/bin/env python3
"""ATIV process/media compatibility checks using the distribution's single tool pair.

No media implementation lives here: fixtures are deterministic PPM/WAV files and
FFmpeg decodes results for assertions. POSIX fake tools exercise error lifecycles.
"""
import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import time
import wave

ROOT = Path(__file__).resolve().parent.parent


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, capture_output=True, **kwargs).stdout


def process_tree():
    if os.name == 'nt':
        command = ['powershell.exe', '-NoProfile', '-Command',
                   'Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress']
        rows = json.loads(run(command))
        return {int(row['ProcessId']): (int(row['ParentProcessId']), row['Name']) for row in rows}
    rows = run(['ps', '-axo', 'pid=,ppid=,comm=']).decode().splitlines()
    return {int(parts[0]): (int(parts[1]), parts[2]) for row in rows if len(parts := row.strip().split(None, 2)) == 3}


def owned_media_processes(parent):
    tree = process_tree()
    owned = {parent}
    for _ in range(8):
        owned |= {pid for pid, (ppid, _) in tree.items() if ppid in owned}
    return {pid for pid in owned - {parent} if 'ffmpeg' in tree[pid][1].lower()}


def assert_reaped(pids):
    deadline = time.monotonic() + 5
    while pids & process_tree().keys() and time.monotonic() < deadline:
        time.sleep(.05)
    assert not pids & process_tree().keys(), 'Cancelled FFmpeg process remained alive'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, default=ROOT / 'target/debug/ativ-engine')
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg'))
    parser.add_argument('--ffprobe', default=shutil.which('ffprobe'))
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--managed', action='store_true', help='Exercise default bundled ATIV discovery for the staged managed engine')
    options = parser.parse_args()
    assert options.ffmpeg and options.ffprobe, 'The distribution FFmpeg/ffprobe pair is required'
    engine = options.engine.resolve()
    ffmpeg, ffprobe = Path(options.ffmpeg).resolve(), Path(options.ffprobe).resolve()
    versions = [run([tool, '-version']).decode().splitlines()[0].split()[2] for tool in (ffmpeg, ffprobe)]
    assert versions[0] == versions[1], versions
    with tempfile.TemporaryDirectory(prefix='ativ contract ü ') as directory:
        root = Path(directory)
        env = dict(os.environ, ATIV_LOG_PATH=str(root / 'private.log'))
        overrides = [] if options.managed else ['--ffmpeg', str(ffmpeg), '--ffprobe', str(ffprobe)]

        def invoke(command, *args, status=0, tools=None, executable=engine):
            result = subprocess.run([str(executable), command, *(str(x) for x in args), *(overrides if tools is None else tools)],
                                    capture_output=True, env=env, timeout=45)
            if result.returncode != status:
                diagnostics = (root / 'private.log').read_text(errors='replace') if (root / 'private.log').exists() else 'No engine diagnostics'
                (ROOT / 'build').mkdir(exist_ok=True)
                (ROOT / 'build/ffmpeg-contract-failure.log').write_text(diagnostics)
                print('Failed fixture operation:', command, args, flush=True)
                print(diagnostics[-16000:], flush=True)
            assert result.returncode == status, (command, result.returncode, result.stdout, result.stderr)
            events = [json.loads(line) for line in result.stdout.splitlines()]
            if status:
                assert events[-1]['event'] == 'error', events
                assert str(root) not in result.stdout.decode(), result.stdout
            return events

        def clean():
            assert not list(root.rglob('.avid-*')), 'Shared staging leak'
            assert not list(root.rglob('.ativ-*')), 'Legacy staging leak'

        def decode(path, kind='video'):
            args = ['-map', '0:v:0', '-pix_fmt', 'rgb24', '-f', 'rawvideo'] if kind == 'video' else ['-map', '0:a:0', '-f', 's16le']
            return run([ffmpeg, '-v', 'error', '-i', path, *args, '-'])

        def info(path):
            return json.loads(run([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]))

        image = root / 'asymmetric artwork ü.ppm'
        image.write_bytes(b'P6\n64 48\n255\n' + bytes(channel for y in range(48) for x in range(64)
                                                   for channel in (x * 4, y * 5, (x * 3 + y * 2) % 256)))
        audio_paths = []
        for channels, rate in [(1, 44100), (2, 48000)]:
            audio = root / f'audio ü {channels}.wav'
            with wave.open(str(audio), 'wb') as wav:
                wav.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
                wav.writeframes(b''.join(struct.pack('<h', round(10000 * math.sin(2 * math.pi * (440 + ch * 110) * i / rate)))
                                         for i in range(rate) for ch in range(channels)))
            audio_paths.append(audio)
        sources = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [image, *audio_paths]}
        version = re.search(r'^version = "([^"]+)"', (ROOT / 'Cargo.toml').read_text(), re.M)[1]
        version = os.environ.get("ATIV_VERSION", version)
        assert run([engine, 'version']).decode() == f'ativ-engine {version}\n'
        expected = (ROOT / 'crates/ativ-engine/tests/fixtures/presets.ndjson').read_bytes().replace(b'\r\n', b'\n')
        assert run([engine, 'presets']) == expected
        presets = json.loads(expected)['items']
        assert len(presets) == 27
        assert invoke('check')[0].keys() == {'event', 'ffmpeg', 'ffprobe'}
        assert invoke('probe', '--audio', audio_paths[0]) == [{'event': 'probe', 'duration_seconds': 1}]
        # Every actual preset remains usable; PNG format does not follow the suffix.
        for index, preset in enumerate(presets):
            preview = root / 'preview.custom'
            assert invoke('preview', '--image', image, '--output', preview, '--width', preset['width'], '--height', preset['height']) == [{'event': 'complete', 'kind': 'preview'}]
            stream = info(preview)['streams'][0]
            assert (stream['codec_name'], stream['width'], stream['height']) == ('png', preset['width'], preset['height'])
        # Five aspect families and all flip combinations, including both layers.
        for width, height in [(160, 90), (90, 160), (120, 120), (160, 120), (120, 150)]:
            original = None
            for horizontal, vertical in [(False, False), (True, False), (False, True), (True, True)]:
                flags = (['--flip-horizontal'] if horizontal else []) + (['--flip-vertical'] if vertical else [])
                args = ['--image', image, '--width', width, '--height', height, *flags]
                preview = root / 'flipped.png'
                invoke('preview', *args, '--output', preview)
                pixels = decode(preview)
                assert len(pixels) == width * height * 3
                if original is None:
                    original = pixels
                else:
                    assert pixels != original, 'Flip had no effect'
                if options.reference:
                    reference = root / 'reference.png'
                    invoke('preview', *args, '--output', reference, executable=options.reference)
                    assert pixels == decode(reference), (width, height, flags)
        for index, (channels, rate, fps, bitrate) in enumerate([(1, 44100, 30, '128k'), (2, 48000, 240, '224k'), (1, 44100, 1, '128000')]):
            audio = audio_paths[channels - 1]
            output = root / f'video {index}.custom'
            output.write_bytes(b'existing output to replace')
            args = ['--image', image, '--audio', audio, '--width', 160, '--height', 90, '--fps', fps, '--audio-bitrate', bitrate, '--flip-horizontal', '--flip-vertical']
            events = invoke('render', *args, '--output', output)
            stages = [e['stage'] for e in events if e['event'] == 'stage']
            assert stages == ['validating', 'probing', 'compositing', 'encoding', 'publishing', 'complete'], stages
            timing = [e for e in events if e['event'] == 'timing']
            assert len(timing) == 1 and timing[0]['success'] and timing[0]['wall_seconds'] > 0
            assert timing[0]['render_mode'] == 'simple'
            progress = [e for e in events if e['event'] == 'progress']
            assert progress and all(e.keys() == {'event', 'elapsed_seconds', 'duration_seconds', 'fraction', 'eta_seconds'} for e in progress)
            assert any(e['fraction'] is not None for e in progress)
            streams = info(output)['streams']
            video, sound = streams
            assert (video['codec_name'], video['pix_fmt'], video['r_frame_rate']) == ('h264', 'yuv420p', f'{fps}/1')
            assert (sound['codec_name'], sound['channels'], int(sound['sample_rate'])) == ('aac', channels, rate)
            assert abs(float(sound['duration']) - 1) < .05
            assert abs(float(video['duration']) - 1) <= 1 / fps + .05
            data = output.read_bytes()
            assert data.index(b'moov') < data.index(b'mdat'), 'faststart missing'
            if options.reference:
                reference = root / 'reference.mp4'
                invoke('render', *args, '--output', reference, executable=options.reference)
                assert decode(output) == decode(reference), 'Decoded video parity'
                assert decode(output, 'audio') == decode(reference, 'audio'), 'Decoded audio parity'
        legacy = root / 'per-frame.mp4'
        invoke('render', '--image', image, '--audio', audio_paths[0], '--output', legacy,
               '--width', 90, '--height', 160, '--fps', 60, '--render-mode', 'current')
        legacy_stream = info(legacy)['streams'][0]
        assert legacy_stream['codec_name'] == 'h264' and legacy_stream['r_frame_rate'] == '60/1'
        assert decode(legacy), 'Per-frame render produced no decodable video'
        output = root / 'preserved.mp4'
        output.write_bytes(b'previous output')
        base = ['--image', image, '--audio', audio_paths[0], '--output', output, '--width', 160, '--height', 90]
        # Exercise cancellation against the real software encoder after it starts.
        long_audio = root / 'long audio ü.wav'
        with wave.open(str(audio_paths[0]), 'rb') as source, wave.open(str(long_audio), 'wb') as target:
            target.setparams(source.getparams())
            target.writeframes(source.readframes(source.getnframes()) * 60)
        process = subprocess.Popen([str(engine), 'render', *(str(x) for x in base), '--audio', str(long_audio),
                                    '--width', '1920', '--height', '1080', *overrides],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        encoding = False
        for line in iter(process.stdout.readline, b''):
            event = json.loads(line)
            if event == {'event': 'stage', 'stage': 'encoding'}:
                encoding = True
                time.sleep(.15)
                break
        assert encoding
        child_pids = owned_media_processes(process.pid)
        assert child_pids, 'Cancellation test must observe an actual FFmpeg child'
        stdout, _ = process.communicate(b'cancel\n', timeout=10)
        assert process.returncode == 130 and json.loads(stdout.splitlines()[-1])['code'] == 'cancelled'
        assert_reaped(child_pids)
        assert output.read_bytes() == b'previous output'
        clean()
        corrupt = root / 'corrupt ü.media'
        corrupt.write_bytes(b'not media')
        for tail in [['--image', corrupt], ['--audio', corrupt], ['--image', root / 'missing'], ['--width', 8194], ['--width', 8192, '--height', 8192], ['--height', 3], ['--width', 0], ['--fps', 241], ['--fps', 0], ['--audio-bitrate', '0k'], ['--audio-bitrate', '1.5k']]:
            invoke('render', *base, *tail, status=1)
            assert output.read_bytes() == b'previous output'
            clean()
        for source in [image, *audio_paths]:
            for kind in ['direct', 'hard', 'symbolic']:
                alias = source if kind == 'direct' else root / f'alias {kind}'
                if kind == 'hard': os.link(source, alias)
                if kind == 'symbolic':
                    try: alias.symlink_to(source)
                    except OSError:
                        print('SKIP symlink: platform permission unavailable')
                        continue
                assert invoke('render', *base, '--audio', audio_paths[0] if source == image else source, '--output', alias, status=1)[-1]['code'] == 'invalid_input'
                if source == image:
                    assert invoke('preview', '--image', image, '--output', alias, '--width', 160, '--height', 90, status=1)[-1]['code'] == 'invalid_input'
                if kind != 'direct': alias.unlink()
        assert invoke('check', tools=['--ffmpeg', str(root / 'missing'), '--ffprobe', str(ffprobe)], status=1)[-1]['code'] == 'media_tools_unavailable'
        if os.name == 'posix':
            fake = root / 'fake'
            fake.mkdir()
            marker = root / 'encoding.started'
            fake_ffmpeg, fake_ffprobe = fake / 'ffmpeg', fake / 'ffprobe'
            def tool(path, body):
                path.write_text('#!/bin/sh\n' + body)
                path.chmod(0o700)
            def setup(mode='ok', dimensions='64x48', duration='N/A'):
                tool(fake_ffprobe, f'''if [ "$1" = -version ]; then echo 'ffprobe version test'; exit; fi
for arg in "$@"; do if [ "$arg" = 'stream=width,height' ]; then echo '{dimensions}'; exit; fi; done
echo '{duration}'
''')
                tool(fake_ffmpeg, f'''if [ "$1" = -version ]; then echo 'ffmpeg version test'; exit; fi
if [ "$2" = -encoders ]; then echo ' V..... libx264 software'; exit; fi
for arg in "$@"; do output="$arg"; done
printf partial > "$output"
printf 'out_time_us=1000000\\nspeed=2x\\nprogress=continue\\n'
touch '{marker}'
if [ '{mode}' = slow ]; then exec sleep 60; fi
if [ '{mode}' = fail ]; then echo 'private deliberate stderr' >&2; exit 7; fi
printf finished > "$output"
''')
            fake_tools = ['--ffmpeg', str(fake_ffmpeg), '--ffprobe', str(fake_ffprobe)]
            setup()
            assert invoke('probe', '--audio', audio_paths[0], tools=fake_tools) == [{'event': 'probe', 'duration_seconds': None}]
            events = invoke('render', *base, tools=fake_tools)
            assert any(e == {'event': 'progress', 'elapsed_seconds': 1, 'duration_seconds': None, 'fraction': None, 'eta_seconds': None} for e in events)
            for dimensions in ['0x48', '32769x1', '8192x8192']:
                setup(dimensions=dimensions)
                assert invoke('preview', '--image', image, '--output', output, '--width', 160, '--height', 90, tools=fake_tools, status=1)[-1]['code'] == 'invalid_input'
            setup('fail')
            output.write_bytes(b'previous output')
            assert invoke('render', *base, tools=fake_tools, status=1)[-1]['code'] == 'media_tool_failed'
            assert 'private deliberate stderr' in (root / 'private.log').read_text()
            assert output.read_bytes() == b'previous output'
            clean()
            # Kill/reap the actual owned fake encoder on the existing stdin protocol.
            setup('slow')
            marker.unlink(missing_ok=True)
            process = subprocess.Popen([str(engine), 'render', *(str(x) for x in base), *fake_tools], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            deadline = time.monotonic() + 10
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            assert marker.exists()
            stdout, _ = process.communicate(b'CaNcEl\n', timeout=5)
            assert process.returncode == 130 and json.loads(stdout.splitlines()[-1])['code'] == 'cancelled'
            assert output.read_bytes() == b'previous output'
            clean()
            # Cancellation while validating tools, before media execution.
            marker.unlink()
            tool(fake_ffmpeg, f"touch '{marker}'\nexec sleep 60\n")
            for command, args in [('check', []), ('probe', ['--audio', audio_paths[0]]), ('preview', ['--image', image, '--output', output, '--width', 160, '--height', 90]), ('render', base)]:
                process = subprocess.Popen([str(engine), command, *(str(x) for x in args), *fake_tools], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                stdout, _ = process.communicate(b'cancel\n', timeout=5)
                assert process.returncode == 130 and json.loads(stdout.splitlines()[-1])['code'] == 'cancelled'
            setup()
            tool(fake_ffprobe, "echo 'ffprobe version different'\n")
            assert invoke('check', tools=fake_tools, status=1)[-1]['code'] == 'media_tools_unavailable'
            tool(fake_ffmpeg, 'echo wrong identity\n')
            assert invoke('check', tools=fake_tools, status=1)[-1]['code'] == 'media_tools_unavailable'
            setup()
            tool(fake_ffmpeg, 'echo private error >&2\nexit 7\n')
            assert invoke('check', tools=fake_tools, status=1)[-1]['code'] == 'media_tools_unavailable'
            setup()
            tool(fake_ffprobe, '''if [ "$1" = -version ]; then echo 'ffprobe version test'; exit; fi
exec sleep 60
''')
            # Default 30-second probe timeout is translated by the engine, no CLI timeout added.
            assert invoke('probe', '--audio', audio_paths[0], tools=fake_tools, status=1)[-1]['code'] == 'media_tool_failed'
            clean()
        for path, digest in sources.items():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, 'Source media changed'
        clean()
    print('ATIV contract/media checks passed (27 presets, 20 previews, 4 exports, failures and process cleanup).')


if __name__ == '__main__':
    main()
