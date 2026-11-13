"""Offline pre-claim eligibility, publisher races and empty-matrix regressions."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import weekly_release_smoke as gate
import release_eligibility as policy
import publish_weekly_assets as publisher
from test_weekly_release_smoke import FakeAPI, SHA, URL, PATTERN, TARGETS, item
from test_publish_weekly_assets import mac_asset, stable_release

READY = {'ATIV_UPDATE_PUBLIC_KEY': base64.b64encode(bytes(32)).decode(),
         'ATIV_WINDOWS_SIGNING_READY': 'true'}


class ReleaseAPI(FakeAPI):
    def __init__(self, releases=None, assets=None):
        super().__init__()
        self.releases = [stable_release()] if releases is None else releases
        self.assets = [mac_asset()] if assets is None else assets
        self.asset_reads = 0

    def request(self, endpoint, payload=None):
        if '/commits/' in endpoint and payload is None:
            return {'sha': SHA}
        return super().request(endpoint, payload)

    def pages(self, endpoint, key=None):
        if endpoint == self.root + '/releases':
            yield from self.releases
        elif endpoint == self.root + '/releases/7/assets':
            self.asset_reads += 1
            yield from self.assets
        else:
            yield from super().pages(endpoint, key)


def select(api, env=None, targets=TARGETS, max_matrix=256):
    g = gate.Gate(api)
    with patch.object(g, 'tags', return_value=[{'tag':'v1.2.3','sha':SHA}]), patch.object(g, 'statuses', return_value={}):
        return g.select(PATTERN, targets, max_matrix=max_matrix,
                        eligibility=policy.PublicationEligibility(api, READY if env is None else env))


class Eligibility(unittest.TestCase):
    def assert_ineligible(self, releases=None, assets=None, env=None, reason=None):
        api = ReleaseAPI(releases, assets)
        matrix, summary = select(api, env)
        self.assertEqual(matrix, {'include': []})
        self.assertEqual(summary['ineligible'], 4)
        if reason: self.assertEqual(summary['eligibility_reasons'], {reason: 4})
        self.assertFalse(api.writes)
        return api

    def test_raw_tag_missing_release_unclaimed(self):
        self.assert_ineligible(releases=[], reason='missing_release')

    def test_draft_prerelease_and_unknown_state_unclaimed(self):
        for change in ({'draft': True}, {'prerelease': True}, {'draft': None}, {'draft': 0}, {'published_at': None}):
            with self.subTest(change=change):
                api = self.assert_ineligible(releases=[stable_release(**change)], reason='unpublished_or_unstable_release')
                self.assertEqual(api.asset_reads, 0)

    def test_exact_version_uploaded_positive_size_and_digest_required(self):
        variants = [[], [{'name':'ATIV-1.2.2-macos-arm64.zip', **{k:v for k,v in mac_asset().items() if k!='name'}}]]
        for change in ({'state':'new'}, {'size':0}, {'size':True}, {'digest':None}, {'digest':'sha256:bad'}, {'name':'ATIV-1.2.3-dev.1-macos-arm64.zip'}):
            variants.append([{**mac_asset(), **change}])
        for assets in variants:
            with self.subTest(assets=assets):
                self.assert_ineligible(assets=assets, reason='missing_qualified_macos_asset')

    def test_intel_mac_asset_also_qualifies_without_enrollment(self):
        api=ReleaseAPI(assets=[{**mac_asset(),'name':'ATIV-1.2.3-macos-intel.zip'}])
        matrix, summary=select(api)
        self.assertEqual(len(matrix['include']),4)
        self.assertEqual(summary['ineligible'],0)
        self.assertEqual(api.asset_reads,1)
        self.assertFalse(api.writes)

    def test_release_and_repository_holds(self):
        self.assert_ineligible(releases=[stable_release(body='Waiting\n<!-- ATIV-RELEASE-HOLD -->')], reason='release_hold')
        self.assert_ineligible(env={**READY,'ATIV_WEEKLY_RELEASE_HOLD':'pause'}, reason='repository_hold')
        # Nonempty means held, even the literal "false". No implicit unholding.
        self.assert_ineligible(env={**READY,'ATIV_WEEKLY_RELEASE_HOLD':'false'}, reason='repository_hold')

    def test_missing_azure_does_not_block_explicitly_unsigned_windows(self):
        for readiness in ('', 'false', 'True', None):
            matrix,summary=select(ReleaseAPI(),{**READY,'ATIV_WINDOWS_SIGNING_READY':readiness})
            self.assertEqual([i['target'] for i in matrix['include']], TARGETS)
            self.assertEqual(summary['ineligible'],0)

    def test_invalid_update_key_skips_all(self):
        for key in ('', 'not base64', base64.b64encode(bytes(31)).decode()):
            self.assert_ineligible(env={**READY,'ATIV_UPDATE_PUBLIC_KEY':key},reason='missing_or_invalid_update_public_key')

    def test_existing_native_asset_or_partial_sidecar_not_claimed(self):
        for suffix in ('', '.sha256'):
            api=ReleaseAPI(assets=[mac_asset(),{'name':'ATIV-1.2.3-linux-x64.AppImage'+suffix}])
            matrix,summary=select(api)
            self.assertEqual(len(matrix['include']),3)
            self.assertNotIn('linux-x64',[i['target'] for i in matrix['include']])
            self.assertEqual(summary['eligibility_reasons'],{'target_asset_already_exists':1})

    def test_existing_signed_or_unsigned_windows_asset_skips_target(self):
        for suffix in ('.zip','.zip.sha256','-unsigned.zip','-unsigned.zip.sha256'):
            matrix,summary=select(ReleaseAPI(assets=[mac_asset(),{'name':'ATIV-1.2.3-windows-x64'+suffix}]))
            self.assertEqual(len(matrix['include']),3)
            self.assertNotIn('windows-x64',[i['target'] for i in matrix['include']])
            self.assertEqual(summary['eligibility_reasons'],{'target_asset_already_exists':1})

    def test_ambiguous_or_malformed_release_assets_skip(self):
        self.assert_ineligible(releases=[stable_release(), stable_release()],reason='ambiguous_release')
        self.assert_ineligible(assets=[mac_asset(),mac_asset()],reason='ambiguous_assets')
        self.assert_ineligible(releases=[stable_release(id=None)],reason='invalid_release_identity')
        self.assert_ineligible(assets=[None],reason='invalid_assets')

    def test_ineligible_pairs_do_not_exhaust_matrix_limit(self):
        matrix,_=select(ReleaseAPI(assets=[mac_asset(),{'name':'ATIV-1.2.3-windows-x64-unsigned.zip'},{'name':'ATIV-1.2.3-windows-arm64.zip'}]),max_matrix=2)
        self.assertEqual(len(matrix['include']),2)

    def test_api_errors_are_not_missing_releases_and_never_write(self):
        api=ReleaseAPI()
        with patch.object(api,'pages',side_effect=gate.GateError('mocked 403')):
            with self.assertRaises(gate.GateError):select(api)
        self.assertFalse(api.writes)

    def test_preclaim_refresh_blocks_hold_or_missing_assets_without_any_write(self):
        for change in ('hold','assets'):
            api=ReleaseAPI();p=policy.PublicationEligibility(api,READY)
            self.assertIsNone(p(item()))
            if change=='hold':api.releases=[stable_release(body=policy.HOLD_MARKER)]
            else:api.assets=[]
            with self.assertRaisesRegex(gate.GateError,'nothing claimed'):
                gate.Gate(api).claim({'include':[item()]},URL,eligibility=p)
            self.assertFalse(api.writes)

    def test_all_pairs_preflight_before_first_claim(self):
        api=ReleaseAPI(assets=[mac_asset(),{'name':'ATIV-1.2.3-windows-x64-unsigned.zip'}]);p=policy.PublicationEligibility(api,READY)
        with self.assertRaises(gate.GateError):
            gate.Gate(api).claim({'include':[item(),item(target='windows-x64')]},URL,eligibility=p)
        self.assertFalse(api.writes)

    def test_moved_tag_is_not_claimed(self):
        api=ReleaseAPI()
        with patch.object(api,'request',return_value={'sha':'b'*40}):
            matrix,summary=select(api)
        self.assertEqual(matrix,{'include':[]})
        self.assertEqual(summary['eligibility_reasons'],{'release_tag_source_changed':4})
        self.assertFalse(api.writes)

    def test_ready_targets_are_claimed_once(self):
        api=ReleaseAPI();matrix,_=select(api)
        gate.Gate(api).claim(matrix,URL,eligibility=policy.PublicationEligibility(api,READY))
        self.assertEqual(len(api.writes),4)
        self.assertTrue(all(payload['state']=='pending' for _,payload in api.writes))

    def test_api_pagination_mac_on_later_page(self):
        api=gate.GitHub('example/project')
        first=[{'name':'other-'+str(i)} for i in range(100)]
        responses=[ [stable_release()], first, [mac_asset()], {'sha':SHA} ]
        with patch.object(api,'request',side_effect=responses) as request:
            self.assertIsNone(policy.PublicationEligibility(api,READY)(item()))
        self.assertTrue(request.call_args_list[-2].args[0].endswith('page=2'))


class PublisherRaces(unittest.TestCase):
    def test_hold_or_tag_move_before_sidecar_stops_further_writes(self):
        for change in ('hold','tag'):
            with tempfile.TemporaryDirectory() as td:
                root=Path(td);name=publisher.identity('v1.2.3','linux-x64');(root/name).write_bytes(b'image')
                publisher.stage(root/'stage',root,'v1.2.3',SHA,'linux-x64')
                uploads=[]
                def gh(*args):
                    if args[0]=='api':
                        if '/commits/' in args[1]:return json.dumps({'sha':'b'*40 if uploads and change=='tag' else SHA})
                        if '/assets?' in args[1]:return json.dumps([mac_asset()])
                        return json.dumps(stable_release(body=policy.HOLD_MARKER if uploads and change=='hold' else ''))
                    if args[1]=='upload':uploads.append(args[3])
                    if args[1]=='download':
                        asset=args[args.index('--pattern')+1]
                        (Path(args[args.index('--dir')+1])/asset).write_bytes((root/'stage'/asset).read_bytes())
                    return ''
                with patch.object(publisher,'gh',side_effect=gh),patch.dict(os.environ,{'GITHUB_REPOSITORY':'example/project','ATIV_WEEKLY_RELEASE_HOLD':''}):
                    with self.assertRaises(ValueError):publisher.publish(root/'stage','v1.2.3',SHA,'linux-x64')
                self.assertEqual(len(uploads),1)

    def test_publisher_requires_mac_and_repository_not_held(self):
        for hold,assets in [('',[]),('pause',[mac_asset()])]:
            with patch.object(publisher,'gh',side_effect=[json.dumps({'sha':SHA}),json.dumps(stable_release()),json.dumps(assets)]) as gh,patch.dict(os.environ,{'ATIV_WEEKLY_RELEASE_HOLD':hold}):
                with self.assertRaises(ValueError):publisher.publication_release('example/project','v1.2.3',SHA)
            self.assertTrue(all(call.args[0]=='api' for call in gh.call_args_list))

    def test_empty_os_matrices_are_independently_guarded(self):
        workflow=(Path(__file__).parents[1]/'workflows/weekly-release-smoke.yml').read_text()
        for system in ('linux','windows'):
            block=workflow.split('  smoke_'+system+':')[1].split('    strategy:')[0]
            self.assertIn("needs.select.outputs.has_"+system+" == 'true'",block)
            self.assertIn('has_'+system+': ${{ steps.partition.outputs.has_'+system+' }}',workflow)
        self.assertIn('--require-publication --claim',workflow)
        self.assertIn("- cron: '17 16 * * 0'",workflow)
        self.assertNotIn('workflow_dispatch:',workflow)
        self.assertNotIn('azure/',workflow)
        self.assertNotIn('AZURE_',workflow)
        self.assertNotIn('id-token:',workflow)
        self.assertIn("Get-AuthenticodeSignature",workflow)
        self.assertIn("$signature.Status -ne 'NotSigned'",workflow)
        self.assertIn('script/validate_package.py',workflow)
        self.assertIn('Smoke-test the extracted Windows application',workflow)

if __name__=='__main__':unittest.main()
