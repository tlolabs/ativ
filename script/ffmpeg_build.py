#!/usr/bin/env python3
"""Native, verified source builds. See runtime/ffmpeg/dependency.json and docs/ffmpeg-source-runtime.md."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'runtime/ffmpeg/dependency.json'
SPEC = json.loads(SPEC_PATH.read_text())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def target_id(value):
    value = value.lower().removesuffix('-deb').removesuffix('-appimage')
    system, arch = value.split('-', 1)
    arch = {'aarch64': 'arm64', 'x64': 'x86_64', 'intel': 'x86_64', 'amd64': 'x86_64'}.get(arch, arch)
    target = f'{system}-{arch}'
    if target not in SPEC['targets']:
        raise ValueError('Unsupported ATIV FFmpeg target: ' + value)
    return target


def native_target():
    system = platform.system().lower()
    system = 'macos' if system == 'darwin' else 'windows' if system.startswith(('windows', 'mingw', 'msys')) else system
    return target_id(system + '-' + platform.machine())


def recipe_digest():
    # Include every recipe/trust input, not unrelated application edits.
    paths = [SPEC_PATH, ROOT / 'runtime/ffmpeg/release-key.asc', Path(__file__), ROOT / 'script/ffmpeg_runtime.py']
    return hashlib.sha256(b''.join(p.read_bytes() for p in paths)).hexdigest()


def output(args, **kwargs):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, **kwargs).strip()


def toolchain(target):
    cc = os.environ.get('CC', 'clang' if target.startswith(('macos', 'windows')) else 'gcc')
    result = {'cc': cc, 'compiler': output([cc, '--version']), 'machine': output([cc, '-dumpmachine']),
              'make': output(['make', '--version']), 'ar': output([os.environ.get('AR', 'ar'), '--version']) if not target.startswith('macos') else output(['xcrun', '--find', 'ar']),
              'platform': platform.platform(), 'python': platform.python_version(),
              'runner_image': os.environ.get('ImageVersion', ''),
              'environment': {k: os.environ.get(k, '') for k in ['CC', 'AR', 'RANLIB', 'CFLAGS', 'CPPFLAGS', 'LDFLAGS', 'SDKROOT', 'DEVELOPER_DIR', 'MSYSTEM']}}
    if target.startswith('macos'):
        result['sdk'] = output(['xcrun', '--show-sdk-version'])
        result['xcode'] = output(['xcodebuild', '-version'])
    elif target.startswith('windows'):
        result['packages'] = output(['pacman', '-Q'])
    else:
        result['linker'] = output(['ld', '--version'])
        result['libc'] = output(['ldd', '--version'])
    return result


def fingerprint(target):
    inputs = {'target': target, 'recipe_sha256': recipe_digest(), 'toolchain': toolchain(target)}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(), inputs


def fetch(url, path, expected=None):
    if not path.exists():
        temporary = path.with_suffix(path.suffix + '.part')
        try:
            with urllib.request.urlopen(url, timeout=90) as response, temporary.open('wb') as stream:
                shutil.copyfileobj(response, stream)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if expected and digest(path) != expected:
        raise ValueError('Source checksum mismatch: ' + path.name)
    return path


def acquire(destination):
    destination.mkdir(parents=True, exist_ok=True)
    sources = {'ffmpeg': SPEC['source'], **SPEC['external_libraries']}
    archives = {}
    for name, record in sources.items():
        archive = fetch(record['url'], destination / record['url'].split('/')[-1], record['sha256'])
        archives[name] = archive
    signature = fetch(SPEC['source']['signature_url'], destination / 'ffmpeg-release.asc')
    with tempfile.TemporaryDirectory(prefix='ativ-gpg-') as directory:
        os.chmod(directory, 0o700)
        gpg = ['gpg', '--homedir', directory, '--batch']
        output(gpg + ['--import', str(ROOT / 'runtime/ffmpeg/release-key.asc')])
        status = output(gpg + ['--status-fd', '1', '--verify', str(signature), str(archives['ffmpeg'])])
        expected = '[GNUPG:] VALIDSIG ' + SPEC['source']['release_key_fingerprint'] + ' '
        if expected not in status:
            raise ValueError('Unexpected FFmpeg release signer')
    return archives, signature, status


def extract(archive, destination):
    destination.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        # Never permit absolute paths, parent traversal, links or special device files.
        for entry in tar.getmembers():
            if entry.name.startswith('/') or '..' in Path(entry.name).parts or not (entry.isfile() or entry.isdir()):
                raise ValueError('Unsafe source archive member: ' + entry.name)
        tar.extractall(destination, filter='data')
    roots = list(destination.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise ValueError('Source archive must contain one root directory')
    return roots[0]


def build(target, clean=False):
    if target != native_target():
        raise ValueError('Run on a native builder for ' + target)
    key, inputs = fingerprint(target)
    destination = ROOT / 'build/ffmpeg' / target
    if destination.exists() and not clean:
        from ffmpeg_runtime import verify
        if json.loads((destination / 'build.json').read_text())['cache_key'] == key:
            verify(destination, target)
            return destination
    archives, signature, status = acquire(ROOT / 'build/ffmpeg-downloads')
    work = ROOT / 'build/ffmpeg-work' / target
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    prefix = work / 'prefix'
    # configure accepts an absolute prefix; map it out of debug/file macros.
    env = dict(os.environ, LC_ALL='C', TZ='UTC', SOURCE_DATE_EPOCH=str(SPEC['source_date_epoch']),
               ZERO_AR_DATE='1', CC=inputs['toolchain']['cc'], PKG_CONFIG_PATH='',
               PKG_CONFIG_LIBDIR=str(prefix / 'lib/pkgconfig'))
    flags = '-O2 -ffile-prefix-map=' + str(work) + '=/ativ-ffmpeg -fdebug-prefix-map=' + str(work) + '=/ativ-ffmpeg'
    env['CFLAGS'] = flags
    env['CPPFLAGS'] = ''
    env['LDFLAGS'] = ''
    if target.startswith('macos'):
        env['MACOSX_DEPLOYMENT_TARGET'] = '13.0'
        env['CFLAGS'] += ' -mmacosx-version-min=13.0'
    if target.startswith('windows'):
        env['AR'] = 'llvm-ar'
        env['RANLIB'] = 'llvm-ranlib'
        env['LDFLAGS'] = '-static -Wl,--no-insert-timestamp'
    commands = []
    with (work / 'build.log').open('w') as log:
        def run(args, cwd):
            commands.append({'directory': str(cwd.relative_to(work)), 'arguments': [str(a) for a in args]})
            print('Building ' + str(cwd.relative_to(work)) + ': ' + str(args[0]), file=__import__('sys').stderr, flush=True)
            subprocess.run([str(a) for a in args], cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        for name in ['zlib', 'x264']:
            source = extract(archives[name], work / name)
            options = SPEC['external_libraries'][name]['configure']
            if name == 'zlib' and target.startswith('windows'):
                run(['make', '-f', 'win32/Makefile.gcc', 'CC=' + env['CC'], 'AR=llvm-ar', 'RC=llvm-windres', 'CFLAGS=' + flags, 'libz.a'], source)
                (prefix / 'lib/pkgconfig').mkdir(parents=True, exist_ok=True)
                (prefix / 'include').mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / 'libz.a', prefix / 'lib/libz.a')
                for header in ['zlib.h', 'zconf.h']:
                    shutil.copy2(source / header, prefix / 'include' / header)
                (prefix / 'lib/pkgconfig/zlib.pc').write_text(f'prefix={prefix}\nlibdir=${{prefix}}/lib\nincludedir=${{prefix}}/include\nName: zlib\nDescription: zlib\nVersion: 1.3.1\nLibs: -L${{libdir}} -lz\nCflags: -I${{includedir}}\n')
            else:
                if name == 'x264' and target.startswith('windows'):
                    options = [*options, '--host=' + ('aarch64' if target.endswith('arm64') else 'x86_64') + '-w64-mingw32']
                run(['bash', 'configure', '--prefix=' + str(prefix), *options], source)
                run(['make', '-j' + str(min(os.cpu_count() or 2, 8))], source)
                run(['make', 'install'], source)
        source = extract(archives['ffmpeg'], work / 'ffmpeg')
        configure = [*SPEC['configure'], *SPEC['targets'][target]['configure'], '--prefix=/ativ-ffmpeg',
                     '--arch=' + SPEC['targets'][target]['arch'], '--target-os=' + SPEC['targets'][target]['os'],
                     '--cc=' + env['CC'], '--pkg-config-flags=--static', '--extra-cflags=-O2 -I../../prefix/include' + (' -mmacosx-version-min=13.0' if target.startswith('macos') else ''),
                     '--extra-ldflags=' + env['LDFLAGS'] + ' -L../../prefix/lib']
        if target.startswith('windows'):
            configure += ['--ar=llvm-ar', '--ranlib=llvm-ranlib']
        env['CFLAGS'] = '-O2'
        run(['bash', 'configure', *configure], source)
        run(['make', '-j' + str(min(os.cpu_count() or 2, 8)), 'ffmpeg' + ('.exe' if target.startswith('windows') else ''), 'ffprobe' + ('.exe' if target.startswith('windows') else '')], source)
    stage = work / 'payload'
    stage.mkdir()
    for name in ['ffmpeg', 'ffprobe']:
        name += '.exe' if target.startswith('windows') else ''
        shutil.copy2(source / name, stage / name)
        os.chmod(stage / name, 0o755)
    shutil.copy2(SPEC_PATH, stage / 'dependency.json')
    shutil.copy2(source / 'ffbuild/config.log', stage / 'config.log')
    shutil.copy2(source / 'config.h', stage / 'config.h')
    source_dir = stage / 'sources'
    source_dir.mkdir()
    for archive in archives.values():
        shutil.copy2(archive, source_dir / archive.name)
    shutil.copy2(signature, source_dir / signature.name)
    shutil.copy2(ROOT / 'runtime/ffmpeg/release-key.asc', source_dir / 'release-key.asc')
    # Redistribute the exact build scripts along with all corresponding source.
    for script in ['ffmpeg_build.py', 'ffmpeg_runtime.py']:
        shutil.copy2(ROOT / 'script' / script, source_dir / script)
    licenses = stage / 'ffmpeg-licenses'
    licenses.mkdir()
    for name in ['ffmpeg', 'x264', 'zlib']:
        src = next((work / name).iterdir())
        for item in src.iterdir():
            if item.is_file() and item.name.upper().startswith(('COPYING', 'LICENSE', 'COPYRIGHT')):
                shutil.copy2(item, licenses / (name + '-' + item.name))
        if name == 'zlib':
            shutil.copy2(src / 'README', licenses / 'zlib-README')
    versions = {n: output([str((stage / n).resolve()), '-version']) for n in ['ffmpeg' + ('.exe' if target.startswith('windows') else ''), 'ffprobe' + ('.exe' if target.startswith('windows') else '')]}
    for name, version in versions.items():
        if version.splitlines()[0].split()[2] != SPEC['source']['version']:
            raise ValueError('Unexpected built version: ' + name)
    capabilities = {}
    for category in ['encoders', 'decoders', 'demuxers', 'muxers', 'filters', 'protocols']:
        capabilities[category] = output([str((stage / next(iter(versions))).resolve()), '-hide_banner', '-' + category])
    for category, required in {'encoders': ['libx264', 'aac', 'png'], 'decoders': ['mp3', 'aac', 'alac', 'flac', 'vorbis', 'opus', 'wmav2', 'png', 'mjpeg', 'webp', 'bmp', 'tiff'], 'filters': ['scale', 'gblur', 'overlay', 'loop', 'hflip', 'vflip', 'aresample']}.items():
        for name in required:
            if name not in capabilities[category].split():
                raise ValueError('Missing runtime capability: ' + name)
    write_json(stage / 'capabilities.json', capabilities)
    linkage = {}
    for name in versions:
        executable = str((stage / name).resolve())
        if target.startswith('macos'):
            report = output(['otool', '-L', executable])
            if any(not line.strip().startswith(('/usr/lib/', '/System/Library/')) for line in report.splitlines()[1:]):
                raise ValueError('Non-system macOS runtime linkage')
        elif target.startswith('windows'):
            report = output(['llvm-objdump', '-p', executable])
            import re
            imports = re.findall(r'DLL Name: (\S+)', report)
            allowed = {'kernel32.dll', 'user32.dll', 'advapi32.dll', 'bcrypt.dll', 'msvcrt.dll', 'ucrtbase.dll', 'ole32.dll', 'shell32.dll'}
            if not imports or any(n.lower() not in allowed and not n.lower().startswith('api-ms-win-') for n in imports):
                raise ValueError('Non-system Windows runtime linkage: ' + repr(imports))
        else:
            report = output(['readelf', '-d', executable])
            import re
            imports = re.findall(r'NEEDED.*?\[(.*?)\]', report)
            if any(n not in {'libc.so.6', 'libm.so.6', 'libpthread.so.0', 'libdl.so.2', 'librt.so.1', 'ld-linux-x86-64.so.2', 'ld-linux-aarch64.so.1'} for n in imports):
                raise ValueError('Non-system Linux runtime linkage: ' + repr(imports))
        linkage[name] = report
    write_json(stage / 'linkage.json', linkage)
    write_json(stage / 'build.json', {**inputs, 'cache_key': key, 'schema': 1, 'owner': 'ATIV', 'source_verification': status,
               'configure': configure, 'commands': commands, 'versions': versions,
               'binary_sha256': {name: digest(stage / name) for name in versions}})
    files = {str(p.relative_to(stage)).replace('\\', '/'): digest(p) for p in sorted(stage.rglob('*')) if p.is_file()}
    write_json(stage / 'payload.json', files)
    from ffmpeg_runtime import verify
    verify(stage, target)
    shutil.rmtree(destination, ignore_errors=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(stage), destination)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['fingerprint', 'build', 'acquire'])
    parser.add_argument('target')
    parser.add_argument('--clean', action='store_true')
    args = parser.parse_args()
    target = target_id(args.target)
    if args.command == 'fingerprint':
        print(fingerprint(target)[0])
    elif args.command == 'acquire':
        print(acquire(ROOT / 'build/ffmpeg-downloads')[2])
    else:
        print(build(target, args.clean))
