#!/usr/bin/env python3
"""Check a real provider's shared model lease using two packaged helper processes.

No model is downloaded. Only a private temporary cache is ever passed to remove.
Selected installed weights are hardlinked, never copied back to the original.
This is a functional lease/cancellation check, not an accuracy benchmark.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time


ENVIRONMENT = {**os.environ, 'PATH': '', 'HF_HUB_OFFLINE': '1'}


def run_request(helper, payload, directory, name):
    request = directory / f'{name}.json'
    request.write_text(json.dumps(payload), encoding='utf-8')
    result = subprocess.run([str(helper), '--request', str(request)], cwd=directory,
                            env=ENVIRONMENT, capture_output=True, timeout=120)
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    return result, events


def success(helper, payload, directory, name):
    result, events = run_request(helper, payload, directory, name)
    completed = [event for event in events if event.get('event') == 'result']
    if result.returncode or len(completed) != 1:
        raise RuntimeError(f'{name} failed ({result.returncode}): {events[-1:]} '
                           f'{result.stderr[-2000:].decode(errors="replace")}')
    return completed[0]


def inventory(directory):
    result = {}
    for root, directories, files in os.walk(directory, followlinks=False):
        for name in directories + files:
            if (Path(root) / name).is_symlink():
                raise RuntimeError('The selected original model contains a symlink.')
        for name in files:
            path = Path(root) / name
            if not path.is_file():
                raise RuntimeError(f'Expected a regular model file: {path}')
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            result[str(path.relative_to(directory))] = {
                'sha256': digest.hexdigest(), 'bytes': path.stat().st_size,
            }
    if not result:
        raise RuntimeError('Original installed model is empty.')
    return result


def hardlink_model(original, target, files):
    target.mkdir(parents=True)
    for relative in files:
        source, destination = original / relative, target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, destination)
        if source.stat().st_ino != destination.stat().st_ino:
            raise RuntimeError('Private cache was not hardlinked as requested.')


def wait_for_loading(worker, timeout):
    """Return only after observing a provider callback executed inside the lease."""
    deadline = time.monotonic() + timeout
    pending = bytearray()
    events = []
    with selectors.DefaultSelector() as selector:
        selector.register(worker.stdout, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            ready = selector.select(min(1, max(0, deadline - time.monotonic())))
            if not ready:
                if worker.poll() is not None:
                    raise RuntimeError('Transcription exited before the in-lease loading callback.')
                continue
            data = os.read(worker.stdout.fileno(), 65536)
            if not data:
                raise RuntimeError(f'Transcription closed output before provider loading: {events[-2:]}')
            pending.extend(data)
            if len(pending) > 16 * 1024 * 1024:
                raise RuntimeError('Helper protocol line exceeded the response limit.')
            while b'\n' in pending:
                line, _, remaining = pending.partition(b'\n')
                pending = bytearray(remaining)
                event = json.loads(line)
                events.append(event)
                if event.get('event') == 'progress' and event.get('message') == 'Loading Whisper':
                    # Freeze only after actual provider startup. The real cross-process
                    # flock remains held, eliminating a false race with a short clip.
                    worker.send_signal(signal.SIGSTOP)
                    _, status = os.waitpid(worker.pid, os.WUNTRACED)
                    if not os.WIFSTOPPED(status):
                        raise RuntimeError('Transcription completed before its live lease could be checked.')
                    return events
                if event.get('event') in ('error', 'result'):
                    raise RuntimeError(f'No live provider lease was observed: {event}')
    raise RuntimeError('Timed out waiting for provider loading inside its model lease.')


def run(helper, cache, audio, output):
    model_id = 'whisper-large-v3'
    report = {'kind': 'cross-process-model-lease-smoke', 'model': model_id,
              'helper': str(helper), 'accuracy_benchmark': False}
    with tempfile.TemporaryDirectory(prefix='ativ-lease-smoke-') as temporary:
        directory = Path(temporary)
        catalog = success(helper, {'operation': 'catalog', 'cachePath': str(cache)}, directory, 'catalog')
        model = next((item for item in catalog['models'] if item['id'] == model_id), None)
        if not model or not model['installed']:
            raise RuntimeError('The original cache needs an installed full Whisper large-v3 model.')
        original = (cache / model_id / model['installationID']).resolve(strict=True)
        if not original.is_relative_to(cache) or original.parent.parent != cache:
            raise RuntimeError('Original model installation escaped the provided managed cache.')
        before = inventory(original)
        private_cache = directory / 'private-cache'
        private_installation = private_cache / model_id / model['installationID']
        hardlink_model(original, private_installation, before)
        if private_cache.resolve() == cache or cache.is_relative_to(private_cache):
            raise RuntimeError('Private cache isolation failed.')

        payload = {'operation': 'transcribe', 'modelID': model_id, 'audioPath': str(audio),
                   'cachePath': str(private_cache), 'language': 'en'}
        request = directory / 'transcribe.json'
        request.write_text(json.dumps(payload), encoding='utf-8')
        with (directory / 'worker-stderr.log').open('wb') as diagnostics:
            worker = subprocess.Popen([str(helper), '--request', str(request)], cwd=directory,
                                      env=ENVIRONMENT, stdout=subprocess.PIPE, stderr=diagnostics)
            try:
                events = wait_for_loading(worker, 180)
                removal, removal_events = run_request(helper,
                    {'operation': 'remove', 'modelID': model_id, 'cachePath': str(private_cache)},
                    directory, 'remove-while-leased')
                errors = [event for event in removal_events if event.get('event') == 'error']
                if (removal.returncode == 0 or len(errors) != 1
                        or 'already in progress' not in errors[0].get('message', '').lower()
                        or not private_installation.is_dir()):
                    raise RuntimeError(f'Removal did not report the real held lease as busy: {removal_events}')
                report['busy_while_provider_loading'] = errors[0]['message']
                report['provider_callback'] = events[-1]['message']
                worker.send_signal(signal.SIGTERM)
                worker.send_signal(signal.SIGCONT)
                remaining, _ = worker.communicate(timeout=900)
                remaining_events = [json.loads(line) for line in remaining.splitlines() if line.strip()]
                if (worker.returncode != 130 or not any(event.get('event') == 'error'
                        and 'cancelled' in event.get('message', '').lower() for event in remaining_events)):
                    raise RuntimeError(f'Expected awaited cancellation exit 130, got {worker.returncode}: {remaining_events[-2:]}')
                report['cancelled_worker_exit'] = worker.returncode
            finally:
                if worker.poll() is None:
                    # Cleanup still waits for the process before unlinking the private
                    # cache. A forced kill is solely a failed-test emergency path.
                    worker.send_signal(signal.SIGTERM)
                    worker.send_signal(signal.SIGCONT)
                    try:
                        worker.communicate(timeout=60)
                    except subprocess.TimeoutExpired:
                        worker.kill()
                        worker.communicate()

        success(helper, {'operation': 'remove', 'modelID': model_id, 'cachePath': str(private_cache)},
                directory, 'remove-after-exit')
        if (private_cache / model_id).exists():
            raise RuntimeError('Private model removal failed after worker exit.')
        if inventory(original) != before:
            raise RuntimeError('Original model data changed during the private-cache smoke test.')
        report.update(status='passed', removal_after_exit='passed', originals_unchanged=True,
                      original_files_checked=len(before), original_bytes_checked=sum(item['bytes'] for item in before.values()))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
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
