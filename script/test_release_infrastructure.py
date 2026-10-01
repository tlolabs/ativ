#!/usr/bin/env python3
import base64, json, tempfile, unittest, os, runpy, zipfile, plistlib
from unittest.mock import patch
from types import SimpleNamespace
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
        artifact=self.root/'ATIV-0.3.0-macos-arm64.zip'
        config=dict(application_id='com.tlolabs.ativ',repository='tlolabs/ativ',version='0.3.0',channel='stable',target='macos-arm64',public_key=base64.b64encode(self.public).decode())
        with zipfile.ZipFile(artifact,'w') as archive:
            archive.writestr('ATIV.app/Contents/Resources/update-config.json',json.dumps(config))
            archive.writestr('ATIV.app/Contents/Info.plist',plistlib.dumps(dict(CFBundleIdentifier='com.tlolabs.ativ',CFBundleVersion='0.3.0',CFBundleShortVersionString='0.3.0',SUPublicEDKey=config['public_key'])))
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
    def test_development_feed_is_retired(self):
        with self.assertRaises(ValueError):
            build(self.root,'0.3.0-dev.42','development','development',self.seed,self.public)
    def test_empty_release_fails(self):
        with self.assertRaises(ValueError):build(self.root,'0.3.0','stable','v0.3.0',self.seed,self.public)

class PublishTests(unittest.TestCase):
    def test_legacy_publisher_cannot_move_tags_or_replace_assets(self):
        script=Path(__file__).with_name('publish_release.py').resolve()
        with patch('subprocess.run') as process:
            with self.assertRaisesRegex(SystemExit,'qualified final packages'):
                runpy.run_path(str(script),run_name='__main__')
            process.assert_not_called()

    def test_release_cannot_use_unpublished_core_candidate(self):
        from application_release import validate, ROOT
        import tomllib
        version=tomllib.loads((ROOT/'Cargo.toml').read_text())['workspace']['package']['version']
        plan={'schema':1,'repository':'tlolabs/ativ','version':version,'tag':'v'+version,'application_revision':'a'*40}
        with self.assertRaisesRegex(ValueError,'unpublished Core'):
            validate(plan,{'qualification_only':True},'a'*40)

class SigningSetupTests(unittest.TestCase):
    def test_only_a_single_developer_id_application_identity_is_accepted(self):
        from configure_macos_signing import developer_identity
        identity = 'Developer ID Application: Example (ABCDE12345)'
        self.assertEqual(developer_identity(f'1) ABC "{identity}"'), (identity, 'ABCDE12345'))
        for output in ['0 valid identities found', '"Apple Development: Example (ABCDE12345)"', f'"{identity}"\n"{identity}"']:
            with self.assertRaises(ValueError):
                developer_identity(output)

    def test_credential_failure_does_not_print_command_or_output(self):
        from configure_macos_signing import run
        failed = SimpleNamespace(returncode=1, stdout=b'', stderr=b'private-password')
        with patch('configure_macos_signing.subprocess.run', return_value=failed):
            with self.assertRaises(RuntimeError) as error:
                run(['notarytool', '--password', 'private-password'], purpose='Authentication')
        self.assertNotIn('private-password', str(error.exception))

if __name__=='__main__':unittest.main()
