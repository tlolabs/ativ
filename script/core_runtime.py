#!/usr/bin/env python3
"""Host layout for Core-owned runtimes. Recipe, download and trust policy stay in Core."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from acquire_core_runtime import ROOT, check_core


def core_api():
    core = check_core()
    sys.path.insert(0, str(core / 'scripts/ffmpeg'))
    import host
    return core, host


def target_id(value):
    value = value.lower().removesuffix('-deb').removesuffix('-appimage')
    os_name, arch = value.split('-', 1)
    arch = {'aarch64': 'arm64', 'x64': 'x86_64', 'intel': 'x86_64', 'amd64': 'x86_64'}.get(arch, arch)
    core = check_core()
    target = f'{os_name}-{arch}'
    spec = json.loads((core / 'runtime/ffmpeg/spec.json').read_text())
    if target not in {entry['id'] for entry in spec['targets']}:
        raise ValueError('Unsupported Core runtime target: ' + value)
    return target


def provision(target):
    core, host = core_api()
    target = target_id(target)
    revision = (ROOT / 'runtime/core-revision').read_text().strip()
    destination = ROOT / 'build/core-runtime' / revision / target
    if not destination.exists():
        result = subprocess.run([sys.executable, str(core / 'scripts/ffmpeg/acquire.py'), target, str(destination)],
                                capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('AVID Core cannot provide the pinned production runtime. '
                               'Publish the qualified runtime/source assets and attestations from Core first.\n' + result.stderr)
    host.verify(destination, target)
    return destination


def source_archive(runtime):
    info = json.loads((runtime / 'SOURCE.json').read_text())
    name = info['asset']
    if Path(name).name != name:
        raise ValueError('Invalid Core source asset name')
    for path in [runtime / name, runtime.parent / name]:
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == info['sha256']:
            return path
    raise ValueError('Core corresponding-source archive is missing or changed')


def stage(target, runtime, binary, candidate=False):
    core, host = core_api()
    target = target_id(target)
    host.verify(runtime, target, candidate)
    source = source_archive(runtime)
    host.stage(runtime, target, binary, candidate)
    shutil.copy2(source, binary / source.name)
    spec = json.loads((runtime / 'spec.json').read_text())
    build = json.loads((runtime / 'build.json').read_text())
    core_version = tomllib.loads((core / 'Cargo.toml').read_text())['package']['version']
    app_version = os.environ.get('ATIV_VERSION') or tomllib.loads((ROOT / 'Cargo.toml').read_text())['workspace']['package']['version']
    report = {'schema': 1, 'ativ_version': app_version, 'avid_core_version': core_version,
              'avid_core_revision': (ROOT / 'runtime/core-revision').read_text().strip(),
              'runtime_build_revision': build['core_revision'], 'ffmpeg_version': spec['source']['version'],
              'runtime_recipe': spec['recipe'], 'target': target, 'architecture': target.split('-', 1)[1],
              'qualification_only': candidate, 'source_asset': source.name}
    (binary / 'ativ-runtime.json').write_text(json.dumps(report, indent=2) + '\n')


def finish(target, binary, metadata):
    # Called after host signing, before sealing the enclosing app/resources.
    _, host = core_api()
    host.record_signed(binary, target_id(target))
    if binary.resolve() == metadata.resolve():
        return
    names = [line.split('  ', 1)[1] for line in (binary / 'SHA256SUMS').read_text().splitlines()]
    names += ['SHA256SUMS', 'signed-payload.json', 'ativ-runtime.json']
    names += [json.loads((binary / 'SOURCE.json').read_text())['asset']]
    if (binary / 'acquisition.json').exists():
        names += ['acquisition.json']
    pair = {'ffmpeg', 'ffprobe', 'ffmpeg.exe', 'ffprobe.exe'}
    for name in names:
        if name in pair:
            continue
        destination = metadata / name
        if destination.exists():
            raise ValueError('Runtime metadata destination already exists: ' + str(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(binary / name), destination)
    # Remove the emptied runtime notice tree from the executable-code directory.
    for path in sorted((binary / 'licenses').rglob('*'), reverse=True):
        if path.is_dir():
            path.rmdir()
    (binary / 'licenses').rmdir()


def validate(target, binary, metadata, runtime=None, candidate=False):
    core, host = core_api()
    target = target_id(target)
    runtime = runtime or provision(target)
    original = host.verify(runtime, target, candidate)
    suffix = '.exe' if target.startswith('windows-') else ''
    pair = {'ffmpeg' + suffix, 'ffprobe' + suffix}
    for name, contents in original.items():
        if name not in pair and (metadata / name).read_bytes() != contents:
            raise ValueError('Packaged Core metadata differs from verified runtime: ' + name)
    signed = json.loads((metadata / 'signed-payload.json').read_text())
    expected = json.loads(original['validation.json'])['binary_sha256']
    if signed['original_binary_sha256'] != expected or signed['target'] != target:
        raise ValueError('Original/signed runtime identity mismatch')
    from binary import machine
    for name in pair:
        data = (binary / name).read_bytes()
        machine(data, target)
        if hashlib.sha256(data).hexdigest() != signed['signed_binary_sha256'][name]:
            raise ValueError('Packaged binary changed after signing: ' + name)
    provenance = json.loads((metadata / 'ativ-runtime.json').read_text())
    spec = json.loads(original['spec.json'])
    version = tomllib.loads((core / 'Cargo.toml').read_text())['package']['version']
    if (provenance['avid_core_version'] != version or
        provenance['avid_core_revision'] != (ROOT / 'runtime/core-revision').read_text().strip() or
        provenance['ffmpeg_version'] != spec['source']['version'] or provenance['runtime_recipe'] != spec['recipe'] or
        provenance['target'] != target or provenance['architecture'] != target.split('-', 1)[1] or
        provenance['runtime_build_revision'] != json.loads(original['build.json'])['core_revision'] or
        provenance['source_asset'] != json.loads(original['SOURCE.json'])['asset'] or
        provenance['qualification_only'] != candidate):
        raise ValueError('Packaged runtime provenance does not match selected Core')
    source_archive(metadata)
    engine = binary / ('ativ-engine' + suffix)
    env = dict(os.environ, PATH='')
    subprocess.run([str(engine.resolve()), 'check'], env=env, check=True, timeout=60)
    subprocess.run([sys.executable, str(ROOT / 'script/test_engine_contract.py'), '--engine', str(engine),
                    '--ffmpeg', str(binary / ('ffmpeg' + suffix)), '--ffprobe', str(binary / ('ffprobe' + suffix)),
                    '--managed'], check=True)
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['provision', 'stage', 'finish', 'validate'])
    parser.add_argument('target')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--metadata', type=Path)
    parser.add_argument('--candidate', action='store_true', help='Explicit local qualification only; never a production fallback')
    args = parser.parse_args()
    if args.mode == 'provision':
        if args.candidate:
            parser.error('Production acquisition never accepts candidates')
        print(provision(args.target))
    elif args.mode == 'stage':
        if args.binary is None or (args.candidate and args.runtime is None):
            parser.error('Stage requires --binary; candidates also require --runtime')
        stage(args.target, args.runtime or provision(args.target), args.binary, args.candidate)
    elif args.mode == 'finish':
        if args.binary is None:
            parser.error('Finish requires --binary')
        finish(args.target, args.binary, args.metadata or args.binary)
    else:
        if args.binary is None:
            parser.error('Validate requires --binary')
        print(json.dumps(validate(args.target, args.binary, args.metadata or args.binary, args.runtime, args.candidate)))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
