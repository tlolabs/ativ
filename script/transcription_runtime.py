#!/usr/bin/env python3
"""Acquire and package the immutable, separately deployed Apple transcription helper.

This is build tooling; Python is never needed by an installed ATIV application.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import shutil
import struct
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'vendor/avid-transcription'
ARCHIVE = 'AVID_CORE_TRANSCRIPTION_SOURCE.tar.gz'
MANIFEST = 'AVID_CORE_TRANSCRIPTION_SOURCE_MANIFEST.json'
SOURCE_REVISION = '8e27a86ec106028d93130de35a35c0eeda7a9ce3'
SOURCE_RELEASE = 'v0.3.3'
SOURCE_SHA256 = '4234053bad548df25c68949265cb32b4052091856e6da6ad2d0710640f8f67ae'
SOURCE = ROOT / 'build/transcription-core'
HELPER_NAME = 'ATIVTranscriptionHelper'
PACKAGE_MANIFEST = 'transcription-package.json'
HELPER_BUNDLE = HELPER_NAME + '.app'


@contextlib.contextmanager
def source_lock(path):
    with path.open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0)
            if not lock.read(1):
                lock.write(b'0')
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_source(directory, manifest):
    expected = {record['path'] for record in manifest['files']}
    directories = {str(parent) for name in expected for parent in PurePosixPath(name).parents if str(parent) != '.'}
    if directory.is_symlink():
        raise ValueError('Reviewed source root must not be a symlink')
    for path in directory.rglob('*'):
        relative = str(path.relative_to(directory))
        # Offline catalog tests can generate bytecode. It is not a Swift package
        # input; tolerate only cache files derived from the two reviewed scripts.
        cache = (relative == 'script/__pycache__' and path.is_dir()) or (
            path.is_file() and path.relative_to(directory).parts[:2] == ('script', '__pycache__') and
            len(path.relative_to(directory).parts) == 3 and path.suffix == '.pyc' and
            any(path.name.startswith(PurePosixPath(name).stem + '.') for name in expected if name.startswith('script/') and name.endswith('.py')))
        if cache and not path.is_symlink():
            continue
        if path.is_symlink() or (path.is_file() and relative not in expected) or (path.is_dir() and relative not in directories):
            raise ValueError(f'Unexpected file or directory in reviewed source: {relative}')
    for record in manifest['files']:
        path = directory / record['path']
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Missing or invalid reviewed source: {record["path"]}')
        if path.stat().st_size != record['size_bytes'] or sha256(path) != record['sha256']:
            raise ValueError(f'Reviewed source hash mismatch: {record["path"]}')


def acquire(vendor=VENDOR, destination=SOURCE):
    manifest = json.loads((vendor / MANIFEST).read_text())
    archive = vendor / ARCHIVE
    if (manifest['source_revision'] != SOURCE_REVISION or
            manifest['source_release_tag'] != SOURCE_RELEASE):
        raise ValueError('Reviewed transcription source release identity mismatch')
    if manifest['source_bundle_sha256'] != SOURCE_SHA256 or sha256(archive) != SOURCE_SHA256:
        raise ValueError('Reviewed transcription archive SHA-256 mismatch')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source_lock(destination.parent / '.transcription-source.lock'):
        if destination.exists():
            verify_source(destination, manifest)
            return destination
        with tempfile.TemporaryDirectory(prefix='.transcription-source-', dir=destination.parent) as temp:
            stage = Path(temp) / 'source'
            stage.mkdir()
            records = {record['path']: record for record in manifest['files']}
            seen = set()
            with tarfile.open(archive, 'r:gz') as bundle:
                for member in bundle:
                    path = PurePosixPath(member.name)
                    if not path.parts or path.parts[0] != 'avid-core-transcription':
                        raise ValueError('Unexpected archive root')
                    relative = PurePosixPath(*path.parts[1:])
                    name = str(relative)
                    if '..' in relative.parts or relative.is_absolute() or name not in records or name in seen or not member.isfile():
                        raise ValueError(f'Unexpected archive member: {member.name}')
                    seen.add(name)
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.extractfile(member) as source, target.open('wb') as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(records[name]['mode'])
            if seen != set(records):
                raise ValueError('Archive does not contain the complete reviewed source')
            verify_source(stage, manifest)
            stage.rename(destination)
    return destination


def build(configuration='release'):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('Transcription helper builds require native Apple silicon macOS')
    acquire()
    scratch = ROOT / ('build/transcription-helper' if configuration == 'debug' else 'build/transcription-helper-release')
    command = ['swift', 'build', '--package-path', str(ROOT / 'platform/transcription-helper'),
               '--scratch-path', str(scratch), '-c', configuration, '--arch', 'arm64',
               '--disable-sandbox', '--cache-path', str(ROOT / 'build/swift-package-cache'),
               '--config-path', str(ROOT / 'build/swift-package-config'),
               '--security-path', str(ROOT / 'build/swift-package-security'),
               '--force-resolved-versions', '--product', HELPER_NAME]
    env = os.environ.copy()
    env['MACOSX_DEPLOYMENT_TARGET'] = '14.0'
    env['CLANG_MODULE_CACHE_PATH'] = str(ROOT / 'build/swift-module-cache')
    env['SWIFTPM_MODULECACHE_OVERRIDE'] = str(ROOT / 'build/swift-module-cache')
    env.setdefault('DEVELOPER_DIR', '/Applications/Xcode.app/Contents/Developer')
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    output = subprocess.check_output(command + ['--show-bin-path'], cwd=ROOT, env=env, text=True)
    return Path(output.strip()), scratch


def macho_deployment(path):
    """Check arm64 identity and report LC_BUILD_VERSION minOS without developer tools."""
    with path.open('rb') as source:
        header = source.read(32)
        if len(header) != 32 or header[:4] != b'\xcf\xfa\xed\xfe' or struct.unpack_from('<I', header, 4)[0] != 0x100000c:
            raise ValueError(f'Expected thin arm64 Mach-O: {path}')
        ncmds = struct.unpack_from('<I', header, 16)[0]
        for _ in range(ncmds):
            command = source.read(8)
            if len(command) != 8:
                raise ValueError(f'Truncated Mach-O load commands: {path}')
            kind, size = struct.unpack('<II', command)
            if size < 8 or size > 1024 * 1024:
                raise ValueError('Invalid Mach-O command size')
            payload = source.read(size - 8)
            if kind == 0x32:  # LC_BUILD_VERSION
                target, minimum = struct.unpack_from('<II', payload)
                if target != 1:
                    raise ValueError('Helper is not a macOS target')
                return (minimum >> 16, (minimum >> 8) & 255, minimum & 255)
    raise ValueError(f'Missing macOS build version: {path}')


def validate_linkage(path, directory):
    """Reject developer paths and unresolved non-system Mach-O library imports."""
    with path.open('rb') as source:
        header = source.read(32)
        if len(header) != 32 or header[:4] != b'\xcf\xfa\xed\xfe':
            raise ValueError(f'Not a thin Mach-O: {path}')
        for _ in range(struct.unpack_from('<I', header, 16)[0]):
            kind, size = struct.unpack('<II', source.read(8))
            if size < 8 or size > 1024 * 1024:
                raise ValueError('Invalid Mach-O command size')
            payload = source.read(size - 8)
            if kind == 0x8000001c:  # LC_RPATH
                offset = struct.unpack_from('<I', payload)[0] - 8
                runtime_path = payload[offset:].split(b'\0', 1)[0].decode('utf-8')
                if runtime_path.startswith('/') and runtime_path != '/usr/lib/swift':
                    raise ValueError(f'Developer runtime search path in helper: {runtime_path}')
            if kind not in (0xc, 0x80000018, 0x8000001f, 0x20, 0x80000023):
                continue
            offset = struct.unpack_from('<I', payload)[0] - 8
            dependency = payload[offset:].split(b'\0', 1)[0].decode('utf-8')
            if dependency.startswith(('/usr/lib/', '/System/Library/')):
                continue
            candidates = []
            for prefix, base in (('@rpath/', directory / 'Contents/Frameworks'),
                                 ('@loader_path/', path.parent),
                                 ('@executable_path/', directory / 'Contents/MacOS')):
                if dependency.startswith(prefix):
                    candidates.append(base / dependency[len(prefix):])
            if not candidates or not any(candidate.is_file() and candidate.resolve().is_relative_to(directory.resolve()) for candidate in candidates):
                raise ValueError(f'Unbundled helper runtime dependency: {dependency}')


def bundle_swift_runtime(directory):
    helper = directory / 'Contents/MacOS' / HELPER_NAME
    frameworks = directory / 'Contents/Frameworks'
    frameworks.mkdir(parents=True, exist_ok=True)
    subprocess.run(['xcrun', 'swift-stdlib-tool', '--copy', '--scan-executable', str(helper),
                    '--platform', 'macosx', '--destination', str(frameworks)], check=True)
    for library in frameworks.glob('*.dylib'):
        architectures = subprocess.check_output(['/usr/bin/lipo', '-archs', str(library)], text=True).split()
        if 'arm64' not in architectures:
            raise ValueError(f'Helper dependency lacks arm64: {library.name}')
        if len(architectures) > 1:
            thin = library.with_suffix('.thin')
            subprocess.run(['/usr/bin/lipo', str(library), '-thin', 'arm64', '-output', str(thin)], check=True)
            thin.replace(library)
    # SwiftPM embeds build and toolchain search paths. Keep the OS runtime path
    # and add the helper's own directory, so old supported systems can load the
    # bundled Swift compatibility library without Xcode or a developer checkout.
    import re
    load_commands = subprocess.check_output(['/usr/bin/otool', '-l', str(helper)], text=True)
    paths = re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset', load_commands)
    edits = []
    for path in paths:
        if path.startswith('/') and path != '/usr/lib/swift':
            edits += ['-delete_rpath', path]
    if '@executable_path/../Frameworks' not in paths:
        edits += ['-add_rpath', '@executable_path/../Frameworks']
    if edits:
        subprocess.run(['/usr/bin/install_name_tool', *edits, str(helper)], check=True)


def license_files(scratch, destination):
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    source_notices = [SOURCE / 'LICENSE', SOURCE / 'apple/AVIDTranscription/MODEL_NOTICES.md',
                      SOURCE / 'apple/AVIDTranscriptionEngines/THIRD_PARTY_NOTICES.md']
    for path in source_notices:
        shutil.copy2(path, destination / path.name)
    shutil.copytree(VENDOR / 'swift-runtime', destination / 'swift-runtime')
    for checkout in sorted((scratch / 'checkouts').iterdir()):
        if not checkout.is_dir():
            continue
        files = []
        for path in sorted(checkout.rglob('*')):
            relative = path.relative_to(checkout)
            if '.git' in relative.parts:
                continue
            if path.is_file() and path.name.upper().startswith(('LICENSE', 'COPYING', 'COPYRIGHT', 'NOTICE')):
                target = destination / checkout.name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                files.append(str(relative))
        if not files:
            raise ValueError(f'Missing dependency license text for {checkout.name}')
        records.append({'package': checkout.name, 'files': files})
    shutil.copy2(ROOT / 'platform/transcription-helper/Package.resolved', destination / 'Package.resolved')
    (destination / 'sdk-licenses.json').write_text(json.dumps(records, indent=2) + '\n')


def seal(directory):
    payload = {'schema': 1, 'source_archive_sha256': SOURCE_SHA256, 'minimum_macos': '14.0',
               'architecture': 'arm64', 'executable': 'Contents/MacOS/' + HELPER_NAME, 'files': {}}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Unexpected helper payload symlink: {path}')
        if path.is_file():
            payload['files'][str(path.relative_to(directory))] = sha256(path)
    # Keep the integrity record outside the nested signature: signing a helper app
    # changes its main executable, so an internal manifest hashing that executable
    # would create a circular seal. The outer application signs this final record.
    manifest = directory.parent.parent / 'Resources' / PACKAGE_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')


def sign(directory, identity='-', *, seal_payload=True):
    # Loose SwiftPM resource bundles contain resources, not executables. Sign each
    # native executable/library first; enclosing ATIV.app is signed by its caller.
    command = ['/usr/bin/codesign', '--force', '--options', 'runtime', '--sign', identity]
    if identity != '-':
        command += ['--timestamp']
    for path in sorted(directory.rglob('*')):
        if path.is_file() and (path.name == HELPER_NAME or path.suffix == '.dylib'):
            subprocess.run(command + [str(path)], check=True)
    for bundle in sorted((directory / 'Contents/Resources').glob('*.bundle')):
        subprocess.run(command + [str(bundle)], check=True)
    subprocess.run(command + [str(directory)], check=True)
    if seal_payload:
        seal(directory)


def stage(app, configuration='release', identity='-'):
    binary, scratch = build(configuration)
    destination = app / 'Contents/Helpers' / HELPER_BUNDLE
    legacy = app / 'Contents/Helpers/transcription'
    if legacy.exists():
        shutil.rmtree(legacy)
    if destination.exists():
        shutil.rmtree(destination)
    resources = destination / 'Contents/Resources'
    executables = destination / 'Contents/MacOS'
    resources.mkdir(parents=True)
    executables.mkdir(parents=True)
    (destination / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundlePackageType': 'APPL', 'CFBundleExecutable': HELPER_NAME,
        'CFBundleIdentifier': 'com.tlolabs.ativ.transcription', 'CFBundleName': HELPER_NAME,
        'CFBundleVersion': '1', 'CFBundleShortVersionString': '1.0',
        'LSMinimumSystemVersion': '14.0', 'LSUIElement': True,
    }))
    shutil.copy2(binary / HELPER_NAME, executables / HELPER_NAME)
    for resource in sorted(binary.iterdir()):
        if resource.suffix == '.bundle' and resource.is_dir():
            shutil.copytree(resource, resources / resource.name)
        elif resource.suffix == '.metallib':
            shutil.copy2(resource, resources / resource.name)
        elif resource.suffix == '.dylib':
            frameworks = destination / 'Contents/Frameworks'
            frameworks.mkdir(exist_ok=True)
            shutil.copy2(resource, frameworks / resource.name)
    license_files(scratch, resources / 'licenses')
    bundle_swift_runtime(destination)
    minimum = macho_deployment(executables / HELPER_NAME)
    if minimum != (14, 0, 0):
        raise ValueError(f'Unexpected helper deployment target: {minimum}; expected macOS 14.0')
    sign(destination, identity)
    validate(app, 'macos-arm64')
    return destination


def validate(app, target):
    directory = app / 'Contents/Helpers' / HELPER_BUNDLE
    legacy = app / 'Contents/Helpers/transcription'
    if legacy.exists():
        raise ValueError('Legacy loose helper payload cannot be packaged')
    if target not in ('macos-arm64', 'macos-aarch64'):
        if directory.exists():
            raise ValueError('Apple silicon transcription helper must not ship on another target')
        return
    resources = directory / 'Contents/Resources'
    info = plistlib.loads((directory / 'Contents/Info.plist').read_bytes())
    if info.get('LSMinimumSystemVersion') != '14.0' or info.get('CFBundleExecutable') != HELPER_NAME:
        raise ValueError('Invalid helper app identity')
    manifest = json.loads((app / 'Contents/Resources' / PACKAGE_MANIFEST).read_text())
    if manifest['source_archive_sha256'] != SOURCE_SHA256 or manifest['architecture'] != 'arm64' or manifest['minimum_macos'] != '14.0':
        raise ValueError('Invalid helper package identity')
    actual = {str(path.relative_to(directory)): sha256(path) for path in directory.rglob('*')
              if path.is_file()}
    if actual != manifest['files'] or any(path.is_symlink() for path in directory.rglob('*')):
        raise ValueError('Helper payload integrity mismatch')
    helper = directory / 'Contents/MacOS' / HELPER_NAME
    if macho_deployment(helper) != (14, 0, 0):
        raise ValueError('Helper minimum OS changed')
    for path in directory.rglob('*'):
        if path.is_file() and (path.name == HELPER_NAME or path.suffix == '.dylib'):
            macho_deployment(path)
            validate_linkage(path, directory)
    catalog = [path for bundle in resources.glob('*.bundle') for path in bundle.rglob('models.json')]
    if len(catalog) != 1:
        raise ValueError('Missing or ambiguous bundled transcription catalog')
    if not (resources / 'licenses/MODEL_NOTICES.md').is_file() or not (resources / 'licenses/THIRD_PARTY_NOTICES.md').is_file():
        raise ValueError('Missing transcription notices')
    # Clean HOME, empty PATH and a relocated package ensure normal discovery cannot
    # depend on source checkout, developer tools, or an existing model cache.
    with tempfile.TemporaryDirectory(prefix='ativ-helper-validate-') as temporary:
        root = Path(temporary)
        relocated = root / HELPER_BUNDLE
        shutil.copytree(directory, relocated)
        # A marker in only the relocated catalog proves Bundle.module used the
        # shipped resources rather than SwiftPM's absolute build-path fallback.
        relative_catalog = catalog[0].relative_to(directory)
        catalog_data = json.loads((relocated / relative_catalog).read_text())
        catalog_data['models'][0]['displayName'] = 'ATIV packaged-resource lookup check'
        (relocated / relative_catalog).write_text(json.dumps(catalog_data))
        # Changing a sealed resource invalidates a Developer ID signature and can
        # stall macOS assessment before the diagnostic process starts. Re-sign
        # only this disposable copy, including its nested code/resources, ad hoc.
        # Keep the shipped helper and its outer integrity record untouched.
        sign(relocated, seal_payload=False)
        request = root / 'request.json'
        request.write_text(json.dumps({'operation': 'catalog'}))
        env = {'PATH': '', 'HOME': str(root), 'TMPDIR': str(root), 'LANG': 'en_US.UTF-8'}
        result = subprocess.run([str(relocated / 'Contents/MacOS' / HELPER_NAME), '--request', str(request)],
                                cwd=root, env=env, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise ValueError(f'Packaged transcription helper failed: {result.stdout[-4000:]} {result.stderr[-4000:]}')
        events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        completed = [event for event in events if event.get('event') == 'result']
        if len(completed) != 1 or len(completed[0].get('models', [])) != 5:
            raise ValueError('Packaged helper did not return the five-model catalog')
        if completed[0]['models'][0]['displayName'] != 'ATIV packaged-resource lookup check':
            raise ValueError('Helper used resources outside its relocated package')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    sub.add_parser('acquire')
    package = sub.add_parser('stage')
    package.add_argument('app', type=Path)
    package.add_argument('--configuration', choices=['debug', 'release'], default='release')
    package.add_argument('--identity', default='-')
    verify = sub.add_parser('validate')
    verify.add_argument('app', type=Path)
    verify.add_argument('target')
    signing = sub.add_parser('sign')
    signing.add_argument('directory', type=Path)
    signing.add_argument('--identity', default='-')
    args = parser.parse_args()
    if args.operation == 'acquire':
        print(acquire())
    elif args.operation == 'stage':
        print(stage(args.app.resolve(), args.configuration, args.identity))
    elif args.operation == 'validate':
        validate(args.app.resolve(), args.target)
    else:
        sign(args.directory, args.identity)


if __name__ == '__main__':
    main()
