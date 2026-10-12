#!/usr/bin/env python3
"""Acquire and package checksum-pinned AVID Core runtimes; never compile FFmpeg."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / 'runtime/core-runtime.json').read_text())


def platform_plan(target):
    from platform_runtime import plan_for
    return plan_for(target)


def selected_plan(target, runtime=None, signed=None):
    """Select only an explicitly pinned platform or legacy archive identity."""
    target = target_id(target)
    platform = platform_plan(target)
    current = platform['targets'][target]
    legacy = PIN['targets'][target]
    if signed is not None:
        archive_hash = signed['original_runtime_archive_sha256']
        if archive_hash == current['sha256']:
            return platform
        if archive_hash == legacy['sha256']:
            return PIN
        raise ValueError('Packaged runtime archive is not pinned for this target')
    if runtime is not None:
        checksum_hash = digest(Path(runtime) / 'SHA256SUMS')
        if checksum_hash == current['checksums_sha256']:
            return platform
        if checksum_hash == legacy['checksums_sha256']:
            return PIN
        raise ValueError('Runtime checksum manifest is not pinned for this target')
    return platform


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def target_id(target):
    target = {'macos-intel':'macos-x86_64','windows-x64':'windows-x86_64','linux-x64':'linux-x86_64','linux-x64-appimage':'linux-x86_64','linux-arm64-appimage':'linux-arm64'}.get(target,target)
    target = target.replace('aarch64', 'arm64')
    if target not in PIN['targets']:
        raise ValueError('Unsupported Core target: ' + target)
    return target


def pair(target):
    return [name + ('.exe' if target.startswith('windows') else '') for name in ['ffmpeg', 'ffprobe']]


def machine(path, target):
    with path.open('rb') as file:
        data = file.read(4096)
    arm = target.endswith('arm64')
    if target.startswith('macos'):
        valid = len(data) >= 8 and data[:4] == b'\xcf\xfa\xed\xfe' and struct.unpack_from('<I', data, 4)[0] == (0x100000c if arm else 0x1000007)
    elif target.startswith('linux'):
        valid = len(data) >= 20 and data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', data, 18)[0] == (183 if arm else 62)
    else:
        offset = struct.unpack_from('<I', data, 60)[0] if len(data) >= 64 else 0
        valid = offset >= 64 and offset + 6 <= len(data) and data[:2] == b'MZ' and data[offset:offset+4] == b'PE\0\0' and struct.unpack_from('<H', data, offset+4)[0] == (0xaa64 if arm else 0x8664)
    if not valid:
        raise ValueError('Wrong runtime architecture: ' + str(path))


def checked_files(metadata, target):
    path = metadata / 'SHA256SUMS'
    if digest(path) != selected_plan(target, runtime=metadata)['targets'][target]['checksums_sha256']:
        raise ValueError('Core checksum manifest differs from pinned artifact')
    files = {}
    for line in path.read_text().splitlines():
        expected, name = line.split('  ', 1)
        if name in files or Path(name).is_absolute() or any(p in ('', '.', '..') for p in name.split('/')) or '\\' in name or len(expected) != 64:
            raise ValueError('Invalid Core checksum path')
        files[name] = expected
    return files


def verify(runtime, target, binary=None, signed=False):
    from core_runtime import verify_directory
    target = target_id(target)
    derivative=json.loads((runtime / 'signed-payload.json').read_text()) if signed else None
    plan=selected_plan(target, runtime=runtime, signed=derivative)
    info=verify_directory(plan, target, runtime, binary=binary, signed=derivative)
    source=runtime / 'corresponding-source.tar.gz' if signed else runtime.parent / plan['targets'][target]['source_archive']
    if digest(source) != plan['targets'][target]['source_sha256']:
        raise ValueError('Core corresponding source mismatch')
    if not signed and plan is not PIN:
        from platform_runtime import verify_cached
        verify_cached(target, runtime.parent)
    return info


def provision(target):
    from core_runtime import candidate, release, require, verify_receipt, digest as core_digest
    target = target_id(target)
    verifier = json.loads((ROOT / 'runtime/core-acquirer.json').read_text())
    require(core_digest(ROOT / 'script/core_runtime.py') == verifier['sha256'], 'Shared Core verifier differs from its pin')
    qualification = os.environ.get('AVID_CORE_QUALIFICATION') == '1'
    if qualification and os.environ.get('GITHUB_EVENT_NAME') in ('push', 'pull_request', 'pull_request_target'):
        raise ValueError('Candidate qualification is limited to deliberate local/manual qualification; never releases or PR artifacts')
    source = os.environ.get('ATIV_CORE_RUNTIME_SOURCE', 'platform')
    require(source in ('platform', 'legacy'), 'Unknown Core runtime source')
    plan = json.loads((ROOT / 'runtime/core-candidate.json').read_text()) if qualification else PIN if source == 'legacy' else platform_plan(target)
    if source == 'legacy' and not qualification:
        print('AVID Core compatibility fallback selected explicitly: ' + PIN['release_tag'], file=__import__('sys').stderr)
    if not qualification and PIN.get('qualification_only'):
        raise ValueError('Core runtime release is not published and pinned yet')
    selected = os.environ.get('ATIV_FFMPEG_RUNTIME')
    if selected:
        runtime = Path(selected).resolve()
        verify(runtime, target)
        require(selected_plan(target, runtime=runtime)['targets'][target]['sha256'] == plan['targets'][target]['sha256'],
                'Selected local runtime differs from requested source')
        return verify_receipt(plan,target,runtime,qualification) if qualification or source == 'legacy' else runtime
    from platform_runtime import record_for, acquire, verify_cached
    tag = 'qualification' if qualification else PIN['release_tag'] if source == 'legacy' else record_for(target)[0]['release_tag']
    destination = ROOT / 'build/core-acquisition' / tag / target
    if destination.exists():
        runtime = destination / plan['targets'][target]['archive'].removesuffix('.tar.gz')
        return verify_receipt(plan,target,runtime,qualification) if qualification or source == 'legacy' else verify_cached(target, destination)
    return candidate(plan, target, destination, qualification=True) if qualification else release(PIN, target, destination) if source == 'legacy' else acquire(target, destination)


def core_identity():
    pin = tomllib.loads((ROOT / 'Cargo.toml').read_text())['workspace']['dependencies']['avid-core']
    packages = tomllib.loads((ROOT / 'Cargo.lock').read_text())['package']
    core, = [package for package in packages if package['name'] == 'avid-core']
    source = f"git+{pin['git']}?rev={pin['rev']}#{pin['rev']}"
    if core['source'] != source or pin['version'] != '=' + core['version'] or pin['rev'] != PIN['revision']:
        raise ValueError('Core lock differs from the runtime pin')
    return dict(version=core['version'], revision=pin['rev'], source=source)


def engine_identity(binary, target):
    engine = binary / ('ativ-engine.exe' if target.startswith('windows') else 'ativ-engine')
    identity = json.loads(subprocess.check_output([str(engine.resolve()), 'build-info'], timeout=30))
    if identity['avid_core'] != core_identity():
        raise ValueError('Packaged engine differs from pinned AVID Core')
    return identity


def stage(target, runtime, binary):
    target = target_id(target)
    verify(runtime, target)
    plan = selected_plan(target, runtime=runtime)
    engine = binary / ('ativ-engine.exe' if target.startswith('windows') else 'ativ-engine')
    subprocess.run([str(engine.resolve()), 'validate-core-runtime', '--runtime', str(runtime.resolve())], check=True, timeout=60)
    binary.mkdir(parents=True, exist_ok=True)
    for item in runtime.iterdir():
        destination = binary / item.name
        if destination.exists():
            raise ValueError('Refusing to overwrite runtime payload: ' + item.name)
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            shutil.copy2(item, destination)
    shutil.copy2(runtime.parent / plan['targets'][target]['source_archive'], binary / 'corresponding-source.tar.gz')
    identity = engine_identity(binary, target)
    write_json(binary / 'ativ-runtime.json', {'schema': 1, 'owner': 'AVID Core', **identity, 'target': target})


def finish(target, binary, metadata):
    target = target_id(target)
    original = binary if (binary / 'SHA256SUMS').exists() else metadata
    plan = selected_plan(target, runtime=original)
    files = checked_files(original, target)
    write_json(original / 'signed-payload.json', {'schema': 1, 'target': target,
               'original_binary_sha256': {name: files[name] for name in pair(target)},
               'signed_binary_sha256': {name: digest(binary / name) for name in pair(target)},
               'transformation': 'platform code signing or identity-preserving staging',
               'signing_identity': os.environ.get('APPLE_SIGN_IDENTITY') or os.environ.get('ENCAP_SIGN_IDENTITY') or os.environ.get('AZURE_SIGNING_ACCOUNT') or 'unconfigured',
               'original_runtime_archive_sha256': plan['targets'][target]['sha256']})
    if original.resolve() != metadata.resolve():
        metadata.mkdir(parents=True, exist_ok=True)
        names = {Path(name).parts[0] for name in files} - set(pair(target))
        names |= {'SHA256SUMS', 'ativ-runtime.json', 'signed-payload.json', 'corresponding-source.tar.gz'}
        for name in sorted(names):
            if (metadata / name).exists():
                raise ValueError('Metadata destination already exists: ' + name)
            shutil.move(str(original / name), metadata / name)


def validate(target, binary, metadata, runtime=None):
    target = target_id(target)
    verify(metadata, target, binary, signed=True)
    provenance = json.loads((metadata / 'ativ-runtime.json').read_text())
    identity = engine_identity(binary, target)
    if provenance != {'schema': 1, 'owner': 'AVID Core', **identity, 'target': target}:
        raise ValueError('Packaged Core/application provenance mismatch')
    if runtime:
        verify(runtime, target)
    engine = binary / ('ativ-engine.exe' if target.startswith('windows') else 'ativ-engine')
    subprocess.run([str(engine.resolve()), 'check'], env=dict(os.environ, PATH=''), check=True, timeout=60)
    if os.environ.get('ATIV_BUILD_ONLY') != '1':
        subprocess.run([__import__('sys').executable, str(ROOT / 'script/test_engine_contract.py'), '--engine', str(engine), '--ffmpeg', str(binary / pair(target)[0]), '--ffprobe', str(binary / pair(target)[1]), '--managed'], check=True)
    return provenance


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['provision', 'key', 'stage', 'finish', 'validate'])
    parser.add_argument('target')
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--metadata', type=Path)
    args = parser.parse_args()
    if args.mode == 'provision':
        print(provision(args.target))
    elif args.mode == 'key':
        target = target_id(args.target)
        print((PIN if os.environ.get('ATIV_CORE_RUNTIME_SOURCE') == 'legacy' else platform_plan(target))['targets'][target]['sha256'])
    elif args.binary is None:
        parser.error('--binary is required')
    elif args.mode == 'stage':
        stage(args.target, args.runtime or provision(args.target), args.binary)
    elif args.mode == 'finish':
        finish(args.target, args.binary, args.metadata or args.binary)
    else:
        print(json.dumps(validate(args.target, args.binary, args.metadata or args.binary, args.runtime)))
