#!/usr/bin/env python3
"""Validate staged resources, target machine types, identity and bundled discovery."""
import argparse,json,os,plistlib,re,struct,subprocess,tomllib
from pathlib import Path
from ffmpeg_runtime import validate as validate_runtime

def machine(path,target):
    data=path.read_bytes()[:4096]
    expected_arm='arm64' in target
    if target.startswith('windows'):
        assert data[:2]==b'MZ',f'{path}: not PE'
        offset=struct.unpack_from('<I',data,60)[0]
        assert data[offset:offset+4]==b'PE\0\0'
        assert struct.unpack_from('<H',data,offset+4)[0]==(0xaa64 if expected_arm else 0x8664),f'{path}: wrong PE machine'
    elif target.startswith('linux'):
        assert data[:4]==b'\x7fELF' and data[4]==2,f'{path}: not ELF64'
        assert struct.unpack_from('<H',data,18)[0]==(183 if expected_arm else 62),f'{path}: wrong ELF machine'
    else:
        assert data[:4]==b'\xcf\xfa\xed\xfe',f'{path}: not Mach-O64'
        assert struct.unpack_from('<I',data,4)[0]==(0x100000c if expected_arm else 0x1000007),f'{path}: wrong Mach-O machine'

def validate_identity(config,target,info=None):
    base=tomllib.loads((Path(__file__).resolve().parents[1]/'Cargo.toml').read_text())['workspace']['package']['version']
    channel=os.environ.get('ATIV_CHANNEL','stable')
    version=os.environ.get('ATIV_VERSION',base)
    assert channel in ('stable','development')
    if channel=='stable':
        assert version==base, 'Stable package version differs from workspace'
    else:
        assert re.fullmatch(re.escape(base)+r'-dev\.[1-9][0-9]*',version), 'Invalid development package version'
    assert config['target']==target and config['channel']==channel
    assert config['version']==version, 'Packaged updater version differs from build identity'
    app_id='com.tlolabs.ativ' + ('.development' if channel=='development' else '')
    assert config['application_id']==app_id and config['repository']=='tlolabs/ativ'
    if info is not None:
        assert info['ATIVDistributionVersion']==version
        assert info['CFBundleShortVersionString']==base
        assert info['CFBundleVersion']==(version.split('-dev.')[1] if channel=='development' else base)
        assert info['CFBundleIdentifier']==app_id
        assert info['SUEnableAutomaticChecks'] and info['SUVerifyUpdateBeforeExtraction']
        suffix='latest/download' if channel=='stable' else 'download/development'
        assert info['SUFeedURL'].endswith(f'{suffix}/appcast-{target}.xml')

def validate(root,target):
    if target.startswith('macos'):
        contents=root/'Contents';binary=contents/'MacOS';icons=[contents/'Resources/ATIV.icns'];names=['ATIV','ativ-engine','ffmpeg','ffprobe']
        info=plistlib.loads((contents/'Info.plist').read_bytes()); assert info['LSMinimumSystemVersion']=='13.0'
        assert info['CFBundleIconFile']=='ATIV'
        assert (contents/'Frameworks/Sparkle.framework').is_dir()
    elif target.startswith('windows'):
        binary=root;icons=[root/'Assets/ATIV.ico'];names=['ATIV.exe','ativ-engine.exe','ativ-update.exe','ffmpeg.exe','ffprobe.exe']
    else:
        binary=root/'usr/lib/ativ'
        if not binary.exists():binary=root/'usr/lib/ativ-development'
        icons=list((root/'usr/share/icons/hicolor/256x256/apps').glob('*.png'));names=['ativ-engine','ativ-update','ffmpeg','ffprobe']
        ui=root/'usr/bin/ativ'
        if not ui.exists():ui=root/'usr/bin/ativ-development'
        assert ui.is_file() and os.access(ui,os.X_OK), 'Missing Linux launcher'
        machine(binary/'ATIV',target)
        assert list((root/'usr/share/applications').glob('*.desktop'))
    assert icons and all(p.is_file() and p.stat().st_size>100 for p in icons),'Missing native icons'
    for name in names: machine(binary/name,target)
    config_path=(contents/'Resources/update-config.json') if target.startswith('macos') else (binary/'update-config.json')
    config=json.loads(config_path.read_text())
    validate_identity(config,target,info if target.startswith('macos') else None)
    # Run in isolation so PATH cannot hide missing bundle dependencies.
    engine=binary/('ativ-engine.exe' if target.startswith('windows') else 'ativ-engine')
    env=os.environ.copy();env['PATH']=''
    result=subprocess.run([str(engine.resolve()),'check'],env=env,capture_output=True,text=True,check=False,timeout=60)
    assert result.returncode == 0, f'Packaged engine check failed: {result.stdout} {result.stderr}'
    assert '"event":"tools"' in result.stdout
    presets=subprocess.run([str(engine.resolve()),'presets'],capture_output=True,text=True,check=True,timeout=20)
    assert len(json.loads(presets.stdout)['items'])==27
    metadata = contents/'Resources/FFmpeg' if target.startswith('macos') else binary/'ffmpeg-runtime'
    provenance = validate_runtime(target, binary, metadata)
    assert provenance['ativ_version'] == config['version'], 'ATIV/runtime provenance version mismatch'
    print(f'Validated {target}: machine types, resources, identity, updater and bundled media discovery')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('target');a=p.parse_args();validate(a.root,a.target)
