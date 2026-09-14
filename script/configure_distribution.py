#!/usr/bin/env python3
"""Write host-owned version/update metadata into a staged package."""
import argparse, base64, json, os, plistlib, re
from datetime import date
from xml.etree import ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def identity():
    base=re.search(r'^version = "([^"]+)"',(ROOT/'Cargo.toml').read_text(),re.M)[1]
    channel=os.environ.get('ATIV_CHANNEL','stable')
    version=os.environ.get('ATIV_VERSION',base)
    if channel not in ('stable','development'): raise ValueError('Invalid channel')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-dev\.\d+)?',version): raise ValueError('Invalid version')
    if (channel=='development') != ('-dev.' in version): raise ValueError('Version must match channel')
    return version,channel

def configure(stage,target):
    version,channel=identity();key=os.environ.get('ATIV_UPDATE_PUBLIC_KEY','')
    if key and len(base64.b64decode(key,validate=True))!=32: raise ValueError('Invalid update public key')
    if os.environ.get('ATIV_RELEASE')=='1' and not key: raise ValueError('Release requires ATIV_UPDATE_PUBLIC_KEY')
    stage.mkdir(parents=True,exist_ok=True)
    config_dir = stage.parent / "Resources" if target.startswith("macos-") else stage
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir/'update-config.json').write_text(json.dumps(dict(version=version,channel=channel,target=target,public_key=key),indent=2)+'\n')
    if channel=='development' and not target.startswith('macos-'): (stage/'development-build').touch()
    if target.startswith('macos-'):
        path=stage.parent/'Info.plist';info=plistlib.loads(path.read_bytes())
        info.update(CFBundleShortVersionString=version.split('-dev.')[0],ATIVDistributionVersion=version,CFBundleVersion=version.split('-dev.')[1] if '-dev.' in version else version,LSMinimumSystemVersion='13.0',SUEnableAutomaticChecks=True,SUAutomaticallyUpdate=False,SUVerifyUpdateBeforeExtraction=True,SUEnableSystemProfiling=False,SUSendProfileInfo=False,SUPublicEDKey=key)
        suffix='latest/download' if channel=='stable' else 'download/development'
        info['SUFeedURL']=f'https://github.com/tlolabs/ativ/releases/{suffix}/appcast-{target}.xml'
        if channel=='development': info.update(CFBundleIdentifier='com.tlolabs.ativ.development',CFBundleDisplayName='ATIV Development',CFBundleName='ATIV Development')
        path.write_bytes(plistlib.dumps(info))
    if target.startswith('linux-'):
        metadata = stage.parents[1] / 'share/metainfo/com.tlolabs.ativ.metainfo.xml'
        if metadata.exists():
            tree=ET.parse(metadata);release=tree.find('.//release')
            if release is not None: release.set('version',version);release.set('date',date.today().isoformat())
            tree.write(metadata,encoding='utf-8',xml_declaration=True)
    return version
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',type=Path);parser.add_argument('target');args=parser.parse_args();print(configure(args.stage,args.target))
