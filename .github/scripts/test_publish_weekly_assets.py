import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import publish_weekly_assets as release
import weekly_release_smoke as gate
from test_weekly_release_smoke import FakeAPI, item, SHA, URL

def mac_asset():
    return {'name': 'ATIV-1.2.3-macos-arm64.zip', 'state': 'uploaded', 'size': 42,
            'digest': 'sha256:' + 'a' * 64}


def stable_release(**changes):
    return {'id': 7, 'tag_name': 'v1.2.3', 'draft': False, 'prerelease': False,
            'published_at': '2026-11-12T10:00:00Z', 'body': '', **changes}


class Assets(unittest.TestCase):
    def test_stage_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); name=release.identity('v1.2.3','linux-x64')
            (root/name).write_bytes(b'qualified')
            release.stage(root/'stage',root,'v1.2.3',SHA,'linux-x64')
            meta=json.loads((root/'stage/qualification.json').read_text())
            self.assertEqual(meta['sha256'],release.digest(root/name))
            with self.assertRaises(FileExistsError): release.stage(root/'stage',root,'v1.2.3',SHA,'linux-x64')
    def test_windows_identity_and_metadata_are_explicitly_unsigned(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            name=release.identity('v1.2.3','windows-x64')
            self.assertEqual(name,'ATIV-1.2.3-windows-x64-unsigned.zip')
            (root/'ATIV-1.2.3-windows-x64.zip').write_bytes(b'qualified unsigned ZIP')
            release.stage(root/'stage',root,'v1.2.3',SHA,'windows-x64')
            meta=json.loads((root/'stage/qualification.json').read_text())
            self.assertEqual(meta['signing'],'unsigned')
            self.assertEqual(meta['name'],name)
            meta['signing']='signed'
            (root/'stage/qualification.json').write_text(json.dumps(meta))
            with patch.object(release,'gh') as api:
                with self.assertRaises(ValueError):release.publish(root/'stage','v1.2.3',SHA,'windows-x64')
                api.assert_not_called()
    def test_invalid_target(self):
        for tag,target in [('v1.0.0','macos-arm64'),('../tag','linux-x64')]:
            with self.assertRaises(ValueError): release.identity(tag,target)
    def test_reject_changed_metadata_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); name=release.identity('v1.2.3','windows-arm64');(root/name.replace('-unsigned.zip','.zip')).write_bytes(b'zip')
            release.stage(root/'stage',root,'v1.2.3',SHA,'windows-arm64')
            (root/'stage'/name).write_bytes(b'tampered')
            with patch.object(release,'gh') as api:
                with self.assertRaises(ValueError):release.publish(root/'stage','v1.2.3',SHA,'windows-arm64')
                api.assert_not_called()
    def test_publish_exact_release_and_download(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); name=release.identity('v1.2.3','linux-x64');(root/name).write_bytes(b'image')
            release.stage(root/'stage',root,'v1.2.3',SHA,'linux-x64')
            calls=[]
            def api(*args):
                calls.append(args)
                if args[0]=='api':
                    if '/commits/' in args[1]:return json.dumps({'sha':SHA})
                    if '/assets?' in args[1]: return json.dumps([mac_asset()])
                    return json.dumps(stable_release())
                if args[1]=='download':
                    asset=args[args.index('--pattern')+1]
                    destination=Path(args[args.index('--dir')+1])/asset
                    destination.write_bytes((root/'stage'/asset).read_bytes())
                return ''
            with patch.object(release,'gh',side_effect=api), patch.dict(os.environ,{'GITHUB_REPOSITORY':'example/project'}):
                release.publish(root/'stage','v1.2.3',SHA,'linux-x64')
            self.assertEqual(len([c for c in calls if c[:2]==('release','upload')]),2)
            self.assertFalse(any('--clobber' in c for c in calls))
    def test_reject_remote_moved_tag(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);name=release.identity('v1.2.3','linux-x64');(root/name).write_bytes(b'image')
            release.stage(root/'stage',root,'v1.2.3',SHA,'linux-x64')
            with patch.object(release,'gh',return_value=json.dumps({'sha':'b'*40})) as api, patch.dict(os.environ,{'GITHUB_REPOSITORY':'example/project'}):
                with self.assertRaises(ValueError):release.publish(root/'stage','v1.2.3',SHA,'linux-x64')
                self.assertEqual(api.call_count,1)
    def test_reject_unpublished_or_unstable_release(self):
        for draft, prerelease in [(True, False), (False, True)]:
            with self.subTest(draft=draft, prerelease=prerelease), tempfile.TemporaryDirectory() as td:
                root=Path(td);name=release.identity('v1.2.3','linux-x64');(root/name).write_bytes(b'image')
                release.stage(root/'stage',root,'v1.2.3',SHA,'linux-x64')
                responses=[json.dumps({'sha':SHA}),json.dumps(stable_release(draft=draft, prerelease=prerelease))]
                with patch.object(release,'gh',side_effect=responses) as api, patch.dict(os.environ,{'GITHUB_REPOSITORY':'example/project'}):
                    with self.assertRaisesRegex(ValueError,'published stable'):release.publish(root/'stage','v1.2.3',SHA,'linux-x64')
                    self.assertEqual(api.call_count,2)
    def test_reject_different_existing_asset_without_upload(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);name=release.identity('v1.2.3','linux-x64');(root/name).write_bytes(b'image')
            release.stage(root/'stage',root,'v1.2.3',SHA,'linux-x64')
            calls=[]
            def api(*args):
                calls.append(args)
                if args[0]=='api':
                    if '/commits/' in args[1]:return json.dumps({'sha':SHA})
                    if '/assets?' in args[1]: return json.dumps([mac_asset(), {'name': name}])
                    return json.dumps(stable_release())
                if args[1]=='download':
                    (Path(args[args.index('--dir')+1])/name).write_bytes(b'other existing asset')
                return ''
            with patch.object(release,'gh',side_effect=api), patch.dict(os.environ,{'GITHUB_REPOSITORY':'example/project'}):
                with self.assertRaisesRegex(ValueError,'overwrite'):release.publish(root/'stage','v1.2.3',SHA,'linux-x64')
            self.assertFalse(any(c[:2]==('release','upload') for c in calls))
    def test_publication_failure_is_not_success(self):
        api=FakeAPI(jobs=[{'name':'Smoke v1.2.3 (linux-x64)','status':'completed','conclusion':'success'}])
        summary=gate.Gate(api).finalize({'include':[item()]},123,1,URL,require_publication=True)
        self.assertEqual(summary['failure'],1)
    def test_publication_success(self):
        api=FakeAPI(jobs=[{'name':f'{kind} v1.2.3 (linux-x64)','status':'completed','conclusion':'success'} for kind in ['Smoke','Publish']])
        summary=gate.Gate(api).finalize({'include':[item()]},123,1,URL,require_publication=True)
        self.assertEqual(summary['success'],1)
if __name__=='__main__':unittest.main()
