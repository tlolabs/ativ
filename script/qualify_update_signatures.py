#!/usr/bin/env python3
"""Verify update signatures against real candidate packages, without publishing a feed."""
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from xml.etree import ElementTree as ET
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from release_metadata import build, SPARKLE
from acquire_core_runtime import ROOT


def main():
    key = Ed25519PublicKey.from_public_bytes(base64.b64decode(os.environ['ATIV_UPDATE_PUBLIC_KEY'], validate=True))
    with tempfile.TemporaryDirectory(prefix='ativ-candidate-signatures-') as temp:
        assets = Path(temp)
        for package in (ROOT / 'packages').iterdir():
            if package.is_file():
                shutil.copy2(package, assets / package.name)
        payload = build(assets, os.environ['ATIV_VERSION'], 'development', 'development',
                        base64.b64decode(os.environ['ATIV_UPDATE_PRIVATE_KEY'], validate=True),
                        base64.b64decode(os.environ['ATIV_UPDATE_PUBLIC_KEY'], validate=True))
        envelope = json.loads((assets / 'latest.json').read_text())
        raw = base64.b64decode(envelope['payload'])
        signature = base64.b64decode(envelope['signature'])
        key.verify(signature, raw)
        try:
            key.verify(signature, raw + b' ')
        except InvalidSignature:
            pass
        else:
            raise AssertionError('Changed update metadata accepted')
        for asset in payload['assets'].values():
            data = (assets / asset['filename']).read_bytes()
            assert len(data) == asset['size'] and hashlib.sha256(data).hexdigest() == asset['sha256']
        for feed in assets.glob('appcast-*.xml'):
            enclosure = ET.parse(feed).find('.//enclosure')
            data = (assets / enclosure.attrib['url'].rsplit('/', 1)[1]).read_bytes()
            signature = base64.b64decode(enclosure.attrib[f'{{{SPARKLE}}}edSignature'])
            key.verify(signature, data)
            try:
                key.verify(signature, data + b'changed')
            except InvalidSignature:
                pass
            else:
                raise AssertionError('Changed Sparkle package accepted')
        root = ROOT / 'build/qualification-evidence'
        root.mkdir(parents=True, exist_ok=True)
        (root / 'update-signatures.json').write_text(json.dumps({
            'status': 'passed', 'scope': 'offline signatures of real candidate packages; not end-to-end update acceptance',
            'metadata_tampering_rejected': True, 'packages': payload['assets'], 'envelope': envelope,
            'public_key': os.environ['ATIV_UPDATE_PUBLIC_KEY'], 'published': False,
        }, indent=2) + '\n')


if __name__ == '__main__':
    main()
