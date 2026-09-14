#!/usr/bin/env python3
"""Generate signed per-channel metadata for only the validated artifacts present."""
import argparse, base64, hashlib, json, os, re
from pathlib import Path
from xml.etree import ElementTree as ET
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
SPARKLE='http://www.andymatuschak.org/xml-namespaces/sparkle'
REPO='https://github.com/tlolabs/ativ'
ET.register_namespace('sparkle',SPARKLE)

def build(assets, version, channel, tag, seed, public_key):
    if channel not in ('stable','development') or not re.fullmatch(r'\d+\.\d+\.\d+(?:-dev\.\d+)?',version):
        raise ValueError('Invalid release version/channel')
    if (channel=='stable' and (tag != 'v'+version or '-dev.' in version)) or (channel=='development' and (tag!='development' or '-dev.' not in version)):
        raise ValueError('Version/tag/channel mismatch')
    key=Ed25519PrivateKey.from_private_bytes(seed)
    if key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)!=public_key: raise ValueError('Update signing keys do not match')
    specs={**{f'macos-{arch}':f'ATIV-{version}-macos-{arch}.dmg' for arch in ('arm64','intel')},
           **{f'windows-{arch}':f'ATIV-{version}-windows-{arch}-setup.exe' for arch in ('x64','arm64')},
           **{f'linux-{arch}-{kind}':f'ATIV-{version}-linux-{arch}.{ext}' for arch in ('x64','arm64') for kind,ext in [('deb','deb'),('appimage','AppImage')]}}
    payload=dict(schema=1,version=version,channel=channel,assets={})
    for target,name in specs.items():
        path=assets/name
        if not path.is_file(): continue
        data=path.read_bytes()
        if not data: raise ValueError('Empty artifact: '+name)
        url=f'{REPO}/releases/download/{tag}/{name}'
        payload['assets'][target]=dict(url=url,filename=name,size=len(data),sha256=hashlib.sha256(data).hexdigest())
        if target.startswith('macos-'):
            root=ET.Element('rss',version='2.0'); feed=ET.SubElement(root,'channel'); ET.SubElement(feed,'title').text=f'ATIV {channel}'
            item=ET.SubElement(feed,'item'); ET.SubElement(item,'title').text='ATIV '+version
            # Development builds use a monotonically increasing numeric bundle version.
            build_version=version.split('-dev.')[1] if '-dev.' in version else version
            ET.SubElement(item,f'{{{SPARKLE}}}version').text=build_version
            ET.SubElement(item,f'{{{SPARKLE}}}shortVersionString').text=version
            ET.SubElement(item,f'{{{SPARKLE}}}minimumSystemVersion').text='13.0'
            ET.SubElement(item,'link').text=f'{REPO}/releases/tag/{tag}'
            ET.SubElement(item,'enclosure',{'url':url,'length':str(len(data)),'type':'application/octet-stream',f'{{{SPARKLE}}}edSignature':base64.b64encode(key.sign(data)).decode()})
            ET.ElementTree(root).write(assets/f'appcast-{target}.xml',encoding='utf-8',xml_declaration=True)
    if not payload['assets']: raise ValueError('No validated release artifacts available')
    raw=json.dumps(payload,separators=(',',':'),sort_keys=True).encode()
    envelope=dict(payload=base64.b64encode(raw).decode(),signature=base64.b64encode(key.sign(raw)).decode())
    (assets/'latest.json').write_text(json.dumps(envelope,indent=2)+'\n')
    return payload

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--assets',type=Path,required=True);parser.add_argument('--version',required=True);parser.add_argument('--channel',required=True);parser.add_argument('--tag',required=True)
    args=parser.parse_args()
    build(args.assets,args.version,args.channel,args.tag,base64.b64decode(os.environ['ATIV_UPDATE_PRIVATE_KEY'],validate=True),base64.b64decode(os.environ['ATIV_UPDATE_PUBLIC_KEY'],validate=True))
    checks=[]
    for p in sorted(args.assets.iterdir()):
        if p.is_file() and p.name!='SHA256SUMS': checks.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name)
    (args.assets/'SHA256SUMS').write_text('\n'.join(checks)+'\n')
if __name__=='__main__':main()
