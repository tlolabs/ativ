#!/usr/bin/env python3
import base64, json, tempfile, unittest, os, runpy
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

class PublishTests(unittest.TestCase):
    def test_partial_release_publishes_available_artifacts(self):
        script=Path(__file__).with_name('publish_release.py').resolve()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'Cargo.toml').write_text('version = "0.3.0"\n')
            assets=root/'release-assets';assets.mkdir();(assets/'ATIV-0.3.0-windows-x64-setup.exe').write_bytes(b'validated installer')
            env={'ATIV_CHANNEL':'stable','GITHUB_REF_NAME':'v0.3.0','GITHUB_SHA':'a'*40,'GITHUB_REPOSITORY':'tlolabs/ativ','GITHUB_ENV':str(root/'env'),'BUILD_RESULTS':json.dumps({'windows':{'result':'success'},'macos':{'result':'failure'}})}
            calls=[]
            def fake_run(args,**kwargs):
                calls.append(args)
                return SimpleNamespace(returncode=1 if args[1:3]==['release','view'] else 0)
            previous=Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ,env),patch('subprocess.run',fake_run):runpy.run_path(str(script),run_name='__main__')
            finally:os.chdir(previous)
            uploads=[call for call in calls if call[1:3]==['release','upload']]
            self.assertEqual(len(uploads),1)
            self.assertTrue(any(str(arg).endswith('windows-x64-setup.exe') for arg in uploads[0]))
            self.assertIn('Incomplete build: macos',(root/'build-release-notes.md').read_text())
            self.assertIn('ATIV_RELEASE_TAG=v0.3.0',(root/'env').read_text())

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
