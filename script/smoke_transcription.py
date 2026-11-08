#!/usr/bin/env python3
"""Exercise the installed helper offline with explicitly provided, verified models.

This is a short functional smoke test, not an accuracy or timing benchmark.
No model is installed/downloaded by this test. Results go only to --output.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def request(helper, payload, directory):
    path = directory / 'request.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    result = subprocess.run([str(helper), '--request', str(path)], cwd=directory,
                            env={**os.environ, 'PATH': '', 'HF_HUB_OFFLINE': '1'},
                            capture_output=True, text=True, timeout=900)
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if result.returncode:
        raise RuntimeError(f'Helper failed ({result.returncode}): {events[-1:]}; {result.stderr[-2000:]}')
    completed = [event for event in events if event.get('event') == 'result']
    if len(completed) != 1:
        raise RuntimeError('Expected one helper result')
    return completed[0]


def check_timed(transcript, offset):
    words = [word for segment in transcript['segments'] for word in segment.get('words', [])]
    if not words:
        raise AssertionError('Expected timed words')
    previous = offset
    for word in words:
        start, end = word['startSeconds'], word['endSeconds']
        assert offset <= start <= end and start >= previous, word
        previous = start
    return len(words)


def run(helper, cache, audio, output):
    output.mkdir(parents=True, exist_ok=True)
    report = {'kind': 'functional-smoke', 'accuracy_benchmark': False, 'results': []}
    with tempfile.TemporaryDirectory(prefix='ativ-model-smoke-') as temporary:
        directory = Path(temporary)
        base = {'audioPath': str(audio), 'cachePath': str(cache), 'language': 'EN_us', 'sourceOffset': 12.5}
        for model in ('whisper-large-v3', 'parakeet-tdt-v3', 'qwen3-asr-1.7b-4bit'):
            value = request(helper, {**base, 'operation': 'transcribe', 'modelID': model}, directory)
            transcript = value['transcript']
            (output / f'{model}.json').write_text(json.dumps(transcript, indent=2), encoding='utf-8')
            assert transcript['provenance']['modelID'] == model
            assert transcript.get('language') == 'en'
            if model.startswith('qwen'):
                assert all(not segment.get('words') for segment in transcript['segments'])
                aligned = request(helper, {**base, 'operation': 'align', 'transcript': transcript,
                    'modelID': 'qwen3-forced-aligner-0.6b-4bit'}, directory)['transcript']
                assert aligned['provenance'] == transcript['provenance']
                assert aligned['alignmentProvenance']['modelID'] == 'qwen3-forced-aligner-0.6b-4bit'
                assert [s['text'] for s in aligned['segments']] == [s['text'] for s in transcript['segments']]
                transcript = aligned
                (output / 'qwen-aligned.json').write_text(json.dumps(aligned, indent=2), encoding='utf-8')
            count = check_timed(transcript, 12.5)
            captions = request(helper, {'operation': 'captions', 'transcript': transcript,
                'captionWindow': {'sourceStartSeconds': 12.5, 'timelineStartSeconds': 0}}, directory)
            assert captions['cues'] and captions['webVTT'].startswith('WEBVTT\n')
            assert 0 <= captions['cues'][0]['startSeconds'] < 2
            (output / f'{model}.srt').write_text(captions['srt'], encoding='utf-8')
            (output / f'{model}.vtt').write_text(captions['webVTT'], encoding='utf-8')
            report['results'].append({'model': model, 'timed_words': count, 'status': 'passed'})
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.helper.resolve(strict=True), args.cache.resolve(strict=True),
        args.audio.resolve(strict=True), args.output.resolve())
