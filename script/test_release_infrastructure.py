#!/usr/bin/env python3
import base64, json, tempfile, unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from release_metadata import build,SPARKLE

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.seed=bytes(range(32));self.key=Ed25519PrivateKey.from_private_bytes(self.seed);self.public=self.key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    def test_partial_release_has_only_passing_targets_and_valid_signatures(self):
        artifact=self.root/'ATIV-0.3.0-macos-arm64.dmg';artifact.write_bytes(b'package fixture')
        payload=build(self.root,'0.3.0','stable','v0.3.0',self.seed,self.public)
        self.assertEqual(list(payload['assets']),['macos-arm64'])
        envelope=json.loads((self.root/'latest.json').read_text())
        self.key.public_key().verify(base64.b64decode(envelope['signature']),base64.b64decode(envelope['payload']))
        enclosure=ET.parse(self.root/'appcast-macos-arm64.xml').find('.//enclosure')
        self.key.public_key().verify(base64.b64decode(enclosure.attrib[f'{{{SPARKLE}}}edSignature']),artifact.read_bytes())
    def test_rejects_channel_tag_and_key_mismatch(self):
        for version,channel,tag in [('0.3.0-dev.1','stable','v0.3.0-dev.1'),('0.3.0','stable','v0.4.0'),('0.3.0','development','development')]:
            with self.assertRaises(ValueError):build(self.root,version,channel,tag,self.seed,self.public)
        with self.assertRaises(ValueError):build(self.root,'0.3.0','stable','v0.3.0',self.seed,bytes(32))
    def test_development_feed_is_separate_and_monotonic(self):
        (self.root/'ATIV-0.3.0-dev.42-macos-intel.dmg').write_bytes(b'development fixture')
        build(self.root,'0.3.0-dev.42','development','development',self.seed,self.public)
        tree=ET.parse(self.root/'appcast-macos-intel.xml')
        self.assertEqual(tree.find(f'.//{{{SPARKLE}}}version').text,'42')
        self.assertIn('/download/development/',tree.find('.//enclosure').attrib['url'])
    def test_empty_release_fails(self):
        with self.assertRaises(ValueError):build(self.root,'0.3.0','stable','v0.3.0',self.seed,self.public)
if __name__=='__main__':unittest.main()
