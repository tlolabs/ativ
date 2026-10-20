#!/usr/bin/env python3
"""Native Core integration diagnostics against ATIV's authenticated runtime.

The runtime must already have been acquired by ffmpeg_runtime.py. This harness
revalidates its provider attestation and bytes; it never discovers system tools.
Fixtures use standard image/audio containers, and only Core constructs media
filter graphs. Each independent diagnostic runs even when another one fails.
"""
import argparse
import binascii
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import struct
import subprocess
import tempfile
import time
import wave
import zlib

from ffmpeg_runtime import ROOT, core_identity, pair, verify
from test_engine_contract import assert_reaped, owned_media_processes


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_artwork(path, width, height):
    path.write_bytes(f'P6\n{width} {height}\n255\n'.encode() + bytes(
        channel for y in range(height) for x in range(width)
        for channel in (x * 251 // width, y * 251 // height, (x * 3 + y * 7) % 256)))


def write_audio(path, seconds):
    rate = 48000
    with wave.open(str(path), 'wb') as audio:
        audio.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
        audio.writeframes(b''.join(struct.pack('<hh',
            round(8000 * math.sin(2 * math.pi * 440 * i / rate)),
            round(6000 * math.sin(2 * math.pi * 660 * i / rate)))
            for i in range(round(rate * seconds))))


def oversized_png(path):
    def chunk(name, body):
        return struct.pack('>I', len(body)) + name + body + struct.pack('>I', binascii.crc32(name + body))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' +
                     chunk(b'IHDR', struct.pack('>IIBBBBB', 32769, 1, 8, 2, 0, 0, 0)) +
                     chunk(b'IDAT', zlib.compress(b'\0' * (32769 * 3 + 1))) + chunk(b'IEND', b''))


def animated_gif(path):
    """Two 0.5-second solid frames; GIF LZW resets avoid a fixture dependency."""
    width, height = 96, 64
    data = b'GIF89a' + struct.pack('<HHBBB', width, height, 128, 0, 0) + bytes([255, 0, 0, 0, 0, 255])
    for index in (0, 1):
        accumulator = count = 0
        compressed = bytearray()
        codes = [code for _ in range(width * height) for code in (4, index)] + [5]
        for code in codes:
            accumulator |= code << count
            count += 3
            while count >= 8:
                compressed.append(accumulator & 255)
                accumulator >>= 8
                count -= 8
        if count:
            compressed.append(accumulator & 255)
        blocks = b''.join(bytes([len(compressed[offset:offset + 255])]) + compressed[offset:offset + 255]
                          for offset in range(0, len(compressed), 255)) + b'\0'
        data += (b'!\xf9\x04\x00\x32\x00\x00\x00' + b',' +
                 struct.pack('<HHHHB', 0, 0, width, height, 0) + b'\x02' + blocks)
    path.write_bytes(data + b';')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, default=ROOT / 'target/debug/ativ-engine')
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--report', type=Path, default=ROOT / 'build/core-0.3.1/native-rendering.json')
    parser.add_argument('--rounds', type=int, default=3)
    options = parser.parse_args()
    if options.rounds < 1:
        parser.error('--rounds must be positive')
    engine, runtime = options.engine.resolve(), options.runtime.resolve()
    report_path = options.report.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg, ffprobe = [runtime / name for name in pair(options.target)]
    report = {'host': platform.platform(), 'target': options.target, 'runtime': str(runtime),
              'engine': str(engine), 'checks': [], 'simulated_checks': 0}

    def case(name, function):
        started = time.perf_counter()
        try:
            detail = function()
            row = {'name': name, 'status': 'passed', 'coverage': 'native', 'detail': detail}
        except Exception as error:  # Diagnostics continue; their aggregate exit remains nonzero.
            row = {'name': name, 'status': 'failed', 'coverage': 'native',
                   'error': f'{type(error).__name__}: {error}'}
        row['wall_seconds'] = time.perf_counter() - started
        report['checks'].append(row)
        print(json.dumps(row), flush=True)
        report_path.write_text(json.dumps(report, indent=2) + '\n')
        return row['status'] == 'passed'

    def run(command, timeout=120):
        result = subprocess.run([str(arg) for arg in command], stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=timeout)
        assert result.returncode == 0, (result.returncode, result.stderr.decode(errors='replace')[-4000:])
        return result.stdout

    def authenticate():
        verify(runtime, options.target)
        identity = json.loads(run([engine, 'build-info']))
        assert identity['avid_core'] == core_identity(), identity
        validated = json.loads(run([engine, 'validate-core-runtime', '--runtime', runtime]))
        assert validated['validated']
        report['core'] = identity['avid_core']
        report['binary_sha256'] = {name: sha256(path) for name, path in
                                    [('engine', engine), ('ffmpeg', ffmpeg), ('ffprobe', ffprobe)]}
        return {'attestation': 'ffmpeg_runtime.verify, including pinned provider attestation',
                'core_directory': validated}

    authenticated = case('authenticated-runtime-and-core-identity', authenticate)
    if authenticated:
        with tempfile.TemporaryDirectory(prefix='native ü ', dir=report_path.parent) as directory:
            work = Path(directory)
            env = dict(os.environ, ATIV_LOG_PATH=str(work / 'private.log'))
            overrides = ['--ffmpeg', str(ffmpeg), '--ffprobe', str(ffprobe)]

            def invoke(command, *arguments, status=0, tools=overrides):
                result = subprocess.run([str(engine), command, *(str(arg) for arg in arguments), *tools],
                                        capture_output=True, env=env, timeout=120)
                assert result.returncode == status, (command, result.returncode,
                    result.stdout.decode(errors='replace')[-4000:], result.stderr.decode(errors='replace')[-1000:])
                events = [json.loads(line) for line in result.stdout.splitlines()]
                if status:
                    assert events[-1]['event'] == 'error', events
                return events

            def probe(path):
                return json.loads(run([ffprobe, '-v', 'error', '-count_frames', '-show_streams',
                                       '-show_format', '-of', 'json', path]))

            def decode(path, sound=False, frame_limit=None):
                args = ['-map', '0:a:0', '-f', 's16le'] if sound else ['-map', '0:v:0', '-pix_fmt', 'rgb24', '-f', 'rawvideo']
                if frame_limit is not None:
                    args += ['-frames:v', frame_limit]
                return run([ffmpeg, '-v', 'error', '-i', path, *args, '-'])

            def no_staging():
                assert not list(work.rglob('.avid-*')), 'Core staging files remain'
                assert not list(work.rglob('.ativ-*')), 'Legacy staging files remain'

            landscape, portrait = work / 'artwork 横 ü.ppm', work / 'artwork 縦 ü.ppm'
            write_artwork(landscape, 96, 64)
            write_artwork(portrait, 64, 96)
            audio = work / 'audio 音 ü.wav'
            write_audio(audio, 1)
            source_hashes = {path: sha256(path) for path in (landscape, portrait, audio)}

            def inspection():
                events = invoke('inspect-image', '--image', landscape, '--image', landscape,
                                '--image', portrait, '--image', landscape)
                expected = [{'event': 'image', 'width': w, 'height': h}
                            for w, h in [(96, 64), (96, 64), (64, 96), (96, 64)]]
                assert events == expected, events
                return {'images_in_one_process': 4, 'dimensions': events,
                        'cache_note': 'Same Renderer handles repeated paths; cache hit counts covered by unit tests.'}
            case('repeated-inspection-shared-renderer', inspection)

            def changed_source():
                changed = work / 'changed source ü.ppm'
                write_artwork(changed, 80, 40)
                before = invoke('inspect-image', '--image', changed)
                write_artwork(changed, 40, 80)
                after = invoke('inspect-image', '--image', changed)
                assert before == [{'event': 'image', 'width': 80, 'height': 40}]
                assert after == [{'event': 'image', 'width': 40, 'height': 80}]
                return {'before': before, 'after': after,
                        'cache_note': 'File replacement between processes; same-Renderer invalidation covered by unit tests.'}
            case('changed-artwork-inspection', changed_source)

            for source in (landscape, portrait):
                for width, height in [(160, 90), (90, 160)]:
                    originals = {}
                    for horizontal, vertical in [(False, False), (True, False), (False, True), (True, True)]:
                        flags = (['--flip-horizontal'] if horizontal else []) + (['--flip-vertical'] if vertical else [])
                        def preview(source=source, width=width, height=height, flags=flags):
                            destination = work / 'preview custom suffix.dat'
                            destination.write_bytes(b'previous preview')
                            events = invoke('preview', '--image', source, '--output', destination,
                                            '--width', width, '--height', height, *flags)
                            assert events[-1] == {'event': 'complete', 'kind': 'preview'}, events
                            assert {'event': 'stage', 'stage': 'complete'} in events, events
                            stream = probe(destination)['streams'][0]
                            assert (stream['codec_name'], stream['width'], stream['height']) == ('png', width, height)
                            pixels = decode(destination)
                            assert len(pixels) == width * height * 3
                            if flags:
                                assert pixels != originals['pixels'], 'Flip did not change artwork'
                            else:
                                originals['pixels'] = pixels
                            no_staging()
                            return {'width': width, 'height': height, 'flip': flags,
                                    'decoded_rgb_sha256': hashlib.sha256(pixels).hexdigest()}
                        case(f'preview-{source.stem}-{width}x{height}-flip-{int(horizontal)}{int(vertical)}', preview)

            def render(output, source=landscape, mode=None, width=160, height=90, fps=30, sound=audio, flags=()):
                arguments = ['--image', source, '--audio', sound, '--output', output, '--width', width,
                             '--height', height, '--fps', fps, '--audio-bitrate', '128k', *flags]
                if mode is not None:
                    arguments += ['--render-mode', mode]
                events = invoke('render', *arguments)
                assert {'event': 'stage', 'stage': 'complete'} in events, events
                timing, = [event for event in events if event['event'] == 'timing']
                assert timing['success']
                no_staging()
                return timing

            for source, width, height, fps in [(landscape, 160, 90, 30), (portrait, 90, 160, 60)]:
                for flags in [(), ('--flip-horizontal', '--flip-vertical')]:
                    def compare(source=source, width=width, height=height, fps=fps, flags=flags):
                        outputs, metadata, timings, pixels, sounds = {}, {}, {}, {}, {}
                        for mode in ('simple', 'current'):
                            output = work / f'{mode}.mp4'
                            timings[mode] = render(output, source, mode, width, height, fps, flags=flags)
                            streams = probe(output)['streams']
                            video = next(stream for stream in streams if stream['codec_type'] == 'video')
                            sound = next(stream for stream in streams if stream['codec_type'] == 'audio')
                            assert (video['codec_name'], video['pix_fmt'], video['width'], video['height']) == ('h264', 'yuv420p', width, height)
                            assert video['r_frame_rate'] == video['avg_frame_rate'] == f'{fps}/1'
                            assert (sound['codec_name'], sound['channels'], sound['sample_rate']) == ('aac', 2, '48000')
                            assert abs(float(sound['duration']) - 1) < .05
                            metadata[mode] = {'video_duration': float(video['duration']),
                                'audio_duration': float(sound['duration']), 'frames': int(video['nb_read_frames']),
                                'frame_rate': video['avg_frame_rate']}
                            assert metadata[mode]['frames'] >= fps
                            timestamps = json.loads(run([ffprobe, '-v', 'error', '-select_streams', 'v:0',
                                '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', output]))['frames']
                            stamps = [float(frame['best_effort_timestamp_time']) for frame in timestamps]
                            assert all(abs((b - a) - 1 / fps) < .000002 for a, b in zip(stamps, stamps[1:])), stamps
                            pixels[mode] = decode(output, frame_limit=fps)
                            sounds[mode] = decode(output, sound=True)
                            outputs[mode] = sha256(output)
                        assert metadata['simple']['frames'] == fps, metadata
                        assert abs(metadata['simple']['video_duration'] - 1) < .002, metadata
                        assert sounds['simple'] == sounds['current'], 'Decoded audio differs'
                        assert len(pixels['simple']) == len(pixels['current']) == width * height * 3 * fps
                        differences = [abs(a - b) for a, b in zip(pixels['simple'], pixels['current'])]
                        mean = sum(differences) / len(differences)
                        assert mean < 2, f'Decoded appearance mean error {mean} exceeds 2 / 255'
                        return {'metadata': metadata, 'timing': timings, 'output_sha256': outputs,
                                'decoded_audio_identical': True, 'overlap_rgb_mean_absolute_error': mean,
                                'overlap_rgb_max_absolute_error': max(differences),
                                'duration_note': 'Core preserves the PerFrame shortest endpoint; Simple bounds output to known audio duration.'}
                    case(f'mode-comparison-{source.stem}-{width}x{height}-{fps}fps-flip-{bool(flags)}', compare)

            for suffix in ['png', 'jpg', 'bmp', 'ppm']:
                def default_mode(suffix=suffix):
                    source = work / f'静止画 ü.{suffix}'
                    if suffix == 'ppm':
                        shutil.copy2(landscape, source)
                    else:
                        run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-i', landscape, '-frames:v', '1', source])
                    timing = render(work / f'default-{suffix}.mp4', source=source)
                    assert timing['render_mode'] == ('current' if suffix == 'ppm' else 'simple'), timing
                    return timing
                case(f'static-{suffix}-default-{"current" if suffix == "ppm" else "simple"}', default_mode)

            for suffix in ['ppm', 'png', 'bmp', 'jpg']:
                def concatenated_animation(suffix=suffix):
                    frames = []
                    for index, color in enumerate((bytes([255, 0, 0]), bytes([0, 0, 255]))):
                        ppm = work / f'animation frame {index}.ppm'
                        ppm.write_bytes(b'P6\n96 64\n255\n' + color * (96 * 64))
                        image = work / f'animation frame {index}.{suffix}'
                        if suffix != 'ppm':
                            run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-i', ppm, '-frames:v', '1', image])
                        frames.append(image.read_bytes())
                    source = work / f'concatenated artwork 動 ü.{suffix}'
                    source.write_bytes(b''.join(frames))
                    data, timings = {}, {}
                    for mode in (None, 'current', 'simple'):
                        output = work / f'concatenated-{suffix}-{mode}.mp4'
                        timings[mode or 'default'] = render(output, source=source, mode=mode)
                        data[mode or 'default'] = decode(output, frame_limit=4)
                    assert timings['default']['render_mode'] == 'current', timings
                    assert data['default'] == data['current'], 'Default changed existing PerFrame pixels'
                    frame_size = 160 * 90 * 3
                    def red_minus_blue(pixels):
                        return [(sum(pixels[offset:offset + frame_size:3]) -
                                 sum(pixels[offset + 2:offset + frame_size:3])) / (160 * 90)
                                for offset in range(0, len(pixels), frame_size)]
                    animated = red_minus_blue(data['default'])
                    static = red_minus_blue(data['simple'])
                    assert max(animated) > 200, animated
                    if suffix != 'jpg':
                        assert min(animated) < -200, animated
                    assert min(static) > 200, static
                    return {'concatenated_encoded_images': 2, 'timings': timings,
                            'default_matches_per_frame_decoded_pixels': True,
                            'default_frame_mean_red_minus_blue': animated,
                            'explicit_simple_frame_mean_red_minus_blue': static,
                            'note': 'The exact runtime renders only the first concatenated JPEG in PerFrame; the default preserves that behavior.' if suffix == 'jpg' else 'Alternating frames remain animated by default.'}
                behavior = 'per-frame-compatibility' if suffix == 'jpg' else 'animation-preserved'
                case(f'concatenated-{suffix}-{behavior}', concatenated_animation)

            def animation_compatibility():
                source = work / 'animated 赤青 ü.gif'
                animated_gif(source)
                assert probe(source)['streams'][0]['nb_read_frames'] == '2'
                destination = work / 'animated destination.mp4'
                results = {}
                for mode in (None, 'current'):
                    destination.write_bytes(b'previous animation destination')
                    arguments = ['--image', source, '--audio', audio, '--output', destination,
                                 '--width', 160, '--height', 90]
                    if mode:
                        arguments += ['--render-mode', mode]
                    events = invoke('render', *arguments, status=1)
                    timing, = [event for event in events if event['event'] == 'timing']
                    assert timing['render_mode'] == 'current' and not timing['success'], timing
                    assert events[-1]['code'] == 'media_tool_failed', events
                    assert destination.read_bytes() == b'previous animation destination'
                    results[mode or 'default'] = {'mode': timing['render_mode'], 'error': events[-1]['code']}
                preview = work / 'animated preview.png'
                invoke('preview', '--image', source, '--output', preview, '--width', 160, '--height', 90)
                assert probe(preview)['streams'][0]['codec_name'] == 'png'
                diagnostic = (work / 'private.log').read_text(errors='replace')
                failure = next((line for line in diagnostic.splitlines() if 'Option loop not found' in line), None)
                report.setdefault('known_limitations', []).append(
                    'The exact runtime probes animated GIF and previews its first frame, but Core PerFrame GIF export fails; default remains PerFrame to preserve existing playback policy. ' + (failure or 'See native diagnostics.'))
                no_staging()
                return {'source_frames': 2, 'render_results': results,
                        'first_frame_preview': 'passed', 'diagnostic': failure}
            case('animated-gif-conservative-default-and-existing-export-limitation', animation_compatibility)

            corrupt, oversized = work / 'corrupt ü.png', work / 'oversized ü.png'
            corrupt.write_bytes(b'not an image')
            oversized_png(oversized)
            preserved = work / 'existing destination ü.mp4'
            for command in ['preview', 'render']:
                for source in [corrupt, oversized, work / 'missing ü.png']:
                    def rejected(command=command, source=source):
                        preserved.write_bytes(b'previous complete output')
                        arguments = ['--image', source, '--output', preserved, '--width', 160, '--height', 90]
                        if command == 'render':
                            arguments += ['--audio', audio]
                        events = invoke(command, *arguments, status=1)
                        assert preserved.read_bytes() == b'previous complete output'
                        no_staging()
                        return {'error_code': events[-1]['code'], 'existing_destination_preserved': True}
                    case(f'{command}-reject-{source.stem}-preserve-destination', rejected)

            for command in ['preview', 'render']:
                for alias_kind in ['direct', 'hard-link', 'symbolic-link']:
                    def protected(command=command, alias_kind=alias_kind):
                        project = work / 'project ü.ativ'
                        project.write_bytes(b'{"schema_version":1}')
                        destination = project
                        if alias_kind != 'direct':
                            destination = work / f'project {command} {alias_kind}.ativ'
                            if alias_kind == 'hard-link':
                                os.link(project, destination)
                            else:
                                destination.symlink_to(project)
                        arguments = ['--image', landscape, '--output', destination, '--protected-path', project,
                                     '--width', 160, '--height', 90]
                        if command == 'render':
                            arguments += ['--audio', audio]
                        events = invoke(command, *arguments, status=1)
                        assert events[-1]['code'] == 'invalid_input', events
                        assert project.read_bytes() == b'{"schema_version":1}'
                        no_staging()
                        return {'error_code': 'invalid_input', 'project_preserved': True, 'alias': alias_kind}
                    case(f'{command}-protected-project-{alias_kind}', protected)

            for tool in ['ffmpeg', 'ffprobe']:
                for damage in ['missing', 'damaged']:
                    def unavailable(tool=tool, damage=damage):
                        path = work / f'{damage}-{tool}'
                        if damage == 'damaged':
                            path.write_bytes(b'damaged executable')
                            path.chmod(0o700)
                        tools = {'ffmpeg': ffmpeg, 'ffprobe': ffprobe} | {tool: path}
                        events = invoke('check', status=1, tools=[
                            '--ffmpeg', str(tools['ffmpeg']), '--ffprobe', str(tools['ffprobe'])])
                        assert events[-1]['code'] == 'media_tools_unavailable'
                        return {'error_code': events[-1]['code']}
                    case(f'{damage}-{tool}-rejected', unavailable)

            def cancellation():
                long_audio = work / 'long audio ü.wav'
                write_audio(long_audio, 60)
                preserved.write_bytes(b'previous complete output')
                process = subprocess.Popen([str(engine), 'render', '--image', str(landscape), '--audio', str(long_audio),
                    '--output', str(preserved), '--width', '1920', '--height', '1080', *overrides],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                try:
                    encoding = False
                    for line in iter(process.stdout.readline, b''):
                        if json.loads(line) == {'event': 'stage', 'stage': 'encoding'}:
                            encoding = True
                            break
                    assert encoding, 'Did not observe native encoding stage'
                    child_pids = set()
                    deadline = time.monotonic() + 5
                    while not child_pids and process.poll() is None and time.monotonic() < deadline:
                        child_pids = owned_media_processes(process.pid)
                        time.sleep(.02)
                    assert child_pids, 'Did not observe an actual owned FFmpeg child'
                    stdout, stderr = process.communicate(b'cancel\n', timeout=10)
                    assert process.returncode == 130, (process.returncode, stdout, stderr)
                    assert json.loads(stdout.splitlines()[-1])['code'] == 'cancelled'
                    assert_reaped(child_pids)
                    assert preserved.read_bytes() == b'previous complete output'
                    no_staging()
                    # A fresh operation has an independent token and succeeds immediately.
                    timing = render(work / 'after cancellation.mp4')
                    return {'cancelled_exit_code': 130, 'native_children_reaped': len(child_pids),
                            'existing_destination_preserved': True, 'next_operation': timing}
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=10)
            case('native-cancellation-and-independent-next-operation', cancellation)

            def preview_cancellation():
                destination = work / 'cancelled preview.png'
                destination.write_bytes(b'previous complete preview')
                process = subprocess.Popen([str(engine), 'preview', '--image', str(landscape),
                    '--output', str(destination), '--width', '1920', '--height', '1080', *overrides],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                stdout, stderr = process.communicate(b'cancel\n', timeout=10)
                assert process.returncode == 130, (process.returncode, stdout, stderr)
                assert json.loads(stdout.splitlines()[-1])['code'] == 'cancelled'
                assert destination.read_bytes() == b'previous complete preview'
                no_staging()
                return {'cancellation': 'requested before preview starts', 'exit_code': 130,
                        'existing_destination_preserved': True}
            case('native-preview-cancellation-preserves-destination', preview_cancellation)

            for command in ('preview', 'render'):
                def late_cancellation(command=command):
                    destination = work / f'published-before-cancel-{command}.media'
                    arguments = [str(engine), command, '--image', str(landscape), '--output', str(destination),
                                 '--width', '160', '--height', '90', *overrides]
                    if command == 'render':
                        arguments += ['--audio', str(audio)]
                    process = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, env=env)
                    seen = []
                    for line in iter(process.stdout.readline, b''):
                        event = json.loads(line)
                        seen.append(event)
                        if event == {'event': 'stage', 'stage': 'complete'}:
                            break
                    assert {'event': 'stage', 'stage': 'complete'} in seen, seen
                    stdout, stderr = process.communicate(b'cancel\n', timeout=10)
                    assert process.returncode == 0, (process.returncode, seen, stdout, stderr)
                    assert probe(destination)['streams'][0]['codec_name'] == ('png' if command == 'preview' else 'h264')
                    no_staging()
                    return {'publication_stage_complete_observed': True, 'late_cancel_exit_code': 0,
                            'published_output_decodable': True}
                case(f'native-{command}-late-cancellation-retains-publication-success', late_cancellation)

            def queued_cancellation():
                long_audio = work / 'queued long audio.wav'
                write_audio(long_audio, 60)
                destination = work / 'shared destination.mp4'
                destination.write_bytes(b'previous shared destination')
                arguments = [str(engine), 'render', '--image', str(landscape), '--audio', str(long_audio),
                    '--output', str(destination), '--width', '1920', '--height', '1080', '--fps', '240', *overrides]
                processes = []
                try:
                    active = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE, env=env)
                    processes.append(active)
                    assert any(json.loads(line) == {'event': 'stage', 'stage': 'encoding'}
                               for line in iter(active.stdout.readline, b'')), 'First render never began encoding'
                    deadline = time.monotonic() + 5
                    active_children = set()
                    while not active_children and active.poll() is None and time.monotonic() < deadline:
                        active_children = owned_media_processes(active.pid)
                        time.sleep(.02)
                    assert active_children, 'No native encoder owned by the first operation'
                    queued = subprocess.Popen(arguments, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                              stderr=subprocess.PIPE, env=env)
                    processes.append(queued)
                    time.sleep(.1)
                    assert queued.poll() is None and active.poll() is None, 'Two renders did not overlap'
                    assert not owned_media_processes(queued.pid), 'Queued operation started a media child'
                    stdout, stderr = queued.communicate(b'cancel\n', timeout=10)
                    assert queued.returncode == 130, (stdout, stderr)
                    assert not any(event['event'] == 'stage' for event in map(json.loads, stdout.splitlines()))
                    assert json.loads(stdout.splitlines()[-1])['code'] == 'cancelled'
                    stdout, stderr = active.communicate(b'cancel\n', timeout=10)
                    assert active.returncode == 130, (stdout, stderr)
                    assert_reaped(active_children)
                    assert destination.read_bytes() == b'previous shared destination'
                    no_staging()
                    return {'same_destination_serialized': True, 'queued_cancellation_exit': 130,
                            'active_cancellation_exit': 130, 'existing_destination_preserved': True}
                finally:
                    for process in processes:
                        if process.poll() is None:
                            try:
                                process.communicate(b'cancel\n', timeout=10)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.communicate(timeout=10)
            case('native-same-output-serialization-and-queued-cancellation', queued_cancellation)

            def performance():
                benchmark_audio = work / 'benchmark 3 seconds.wav'
                write_audio(benchmark_audio, 3)
                benchmark_image = work / 'benchmark 1200x800.ppm'
                write_artwork(benchmark_image, 1200, 800)
                rows = []
                for iteration in range(options.rounds + 1):
                    for mode in [('simple', 'current'), ('current', 'simple')][iteration % 2]:
                        started = time.perf_counter()
                        timing = render(work / f'performance-{mode}.mp4', source=benchmark_image, mode=mode,
                                        width=1920, height=1080, fps=30, sound=benchmark_audio)
                        rows.append({'mode': mode, 'warmup': iteration == 0,
                                     'wall_seconds': time.perf_counter() - started, 'engine': timing})
                medians = {mode: statistics.median(row['wall_seconds'] for row in rows
                    if row['mode'] == mode and not row['warmup']) for mode in ('simple', 'current')}
                media, decoded_frames, decoded_audio = {}, {}, {}
                for mode in ('simple', 'current'):
                    output = work / f'performance-{mode}.mp4'
                    streams = probe(output)['streams']
                    video = next(stream for stream in streams if stream['codec_type'] == 'video')
                    sound = next(stream for stream in streams if stream['codec_type'] == 'audio')
                    media[mode] = {'video_duration': float(video['duration']), 'audio_duration': float(sound['duration']),
                                   'frames': int(video['nb_read_frames']), 'frame_rate': video['avg_frame_rate'],
                                   'width': video['width'], 'height': video['height']}
                    assert (video['width'], video['height']) == (1920, 1080)
                    assert video['avg_frame_rate'] == '30/1'
                    assert abs(float(sound['duration']) - 3) < .05
                    decoded_frames[mode] = [line for line in run([ffmpeg, '-v', 'error', '-i', output,
                        '-map', '0:v:0', '-f', 'framemd5', '-']).decode().splitlines() if not line.startswith('#')]
                    decoded_audio[mode] = decode(output, sound=True)
                assert media['simple']['frames'] == 90
                assert decoded_audio['simple'] == decoded_audio['current']
                return {'rounds': options.rounds, 'warmup_rounds': 1, 'runs': rows, 'median_seconds': medians,
                        'media': media, 'decoded_audio_identical': True,
                        'all_decoded_frame_hashes_and_timestamps_identical': decoded_frames['simple'] == decoded_frames['current'],
                        'settings': {'width': 1920, 'height': 1080, 'source_width': 1200, 'source_height': 800,
                                     'fps': 30, 'audio_bitrate': '128k',
                                     'audio_seconds': 3, 'encoding': 'software H.264/AAC'},
                        'note': 'Application wall time includes runtime validation, probing and atomic publication. Core retains its legacy PerFrame endpoint rules; actual frame counts and decoded parity are reported above.'}
            case('native-mode-performance', performance)
            def source_preservation():
                assert all(sha256(path) == digest for path, digest in source_hashes.items()), 'Source changed'
                no_staging()
                return {'source_files_unchanged': len(source_hashes)}
            case('source-preservation-and-staging-cleanup', source_preservation)
    else:
        report['skipped'] = ['Native media diagnostics require successful runtime authentication.']
    report['counts'] = {'native_passed': sum(check['status'] == 'passed' for check in report['checks']),
                        'native_failed': sum(check['status'] == 'failed' for check in report['checks']),
                        'simulated': 0}
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'report': str(report_path), **report['counts']}), flush=True)
    return int(bool(report['counts']['native_failed']))


if __name__ == '__main__':
    raise SystemExit(main())
