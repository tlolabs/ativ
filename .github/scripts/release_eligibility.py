"""Read-only publication prerequisites shared by selection and publication.

No release is enrolled manually: publishing a stable release with its qualified
Mac ZIP enables eligible native targets. Ineligible work never acquires a claim.
"""
import base64
import binascii
import os
import re

STABLE_TAG = r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
HOLD_MARKER = '<!-- ativ-release-hold -->'


def release_reason(release, tag, assets, hold=''):
    if hold.strip():
        return 'repository_hold'
    if not isinstance(release, dict) or release.get('tag_name') != tag:
        return 'missing_release'
    if (release.get('draft') is not False or release.get('prerelease') is not False
            or not isinstance(release.get('published_at'), str) or not release['published_at']):
        return 'unpublished_or_unstable_release'
    body = release.get('body')
    if body is not None and not isinstance(body, str):
        return 'invalid_release_notes'
    if HOLD_MARKER in (body or '').lower():
        return 'release_hold'
    if not re.fullmatch(STABLE_TAG, tag):
        return 'invalid_stable_tag'
    if not isinstance(assets, list) or any(not isinstance(a, dict) for a in assets):
        return 'invalid_assets'
    names = [a.get('name') for a in assets]
    if any(not isinstance(name, str) for name in names) or len(names) != len(set(names)):
        return 'ambiguous_assets'
    mac_names = {f'ATIV-{tag[1:]}-macos-{arch}.zip' for arch in ('arm64', 'intel')}
    for asset in assets:
        if (asset['name'] in mac_names and asset.get('state') == 'uploaded'
                and type(asset.get('size')) is int and asset['size'] > 0
                and isinstance(asset.get('digest'), str)
                and re.fullmatch(r'sha256:[0-9a-f]{64}', asset['digest'])):
            return None
    return 'missing_qualified_macos_asset'


def configuration_reason(target, env):
    if env.get('ATIV_WEEKLY_RELEASE_HOLD', '').strip():
        return 'repository_hold'
    key = env.get('ATIV_UPDATE_PUBLIC_KEY', '')
    try:
        valid_key = len(base64.b64decode(key, validate=True)) == 32
    except (ValueError, binascii.Error):
        valid_key = False
    if not valid_key:
        return 'missing_or_invalid_update_public_key'
    return None


class PublicationEligibility:
    def __init__(self, api, env=None):
        self.api = api
        self.env = os.environ if env is None else env
        self.refresh()

    def refresh(self):
        self.releases = None
        self.assets = {}
        self.commits = {}

    def __call__(self, item):
        reason = configuration_reason(item['target'], self.env)
        if reason:
            return reason
        if self.releases is None:
            # A complete paginated list distinguishes a raw tag from a release
            # without treating HTTP/authentication errors as a missing release.
            self.releases = {}
            for release in self.api.pages(f'{self.api.root}/releases'):
                if not isinstance(release, dict) or not isinstance(release.get('tag_name'), str):
                    raise ValueError('Malformed release enumeration; nothing may be claimed')
                self.releases.setdefault(release['tag_name'], []).append(release)
        matches = self.releases.get(item['tag'], [])
        if not matches:
            return 'missing_release'
        if len(matches) != 1:
            return 'ambiguous_release'
        release = matches[0]
        # Reject holds/drafts without reading their assets.
        reason = release_reason(release, item['tag'], [])
        if reason != 'missing_qualified_macos_asset':
            return reason
        identifier = release.get('id')
        if type(identifier) is not int or identifier <= 0:
            return 'invalid_release_identity'
        if identifier not in self.assets:
            self.assets[identifier] = list(self.api.pages(f'{self.api.root}/releases/{identifier}/assets'))
        assets = self.assets[identifier]
        reason = release_reason(release, item['tag'], assets)
        if reason:
            return reason
        name = f"ATIV-{item['tag'][1:]}-{item['target']}." + ('zip' if item['target'].startswith('windows-') else 'AppImage')
        # Do not consume a fresh claim to rebuild an already published/partial
        # target. Different bytes cannot be overwritten by the publisher anyway.
        names = {name, name + '.sha256'}
        if item['target'].startswith('windows-'):
            unsigned = name.removesuffix('.zip') + '-unsigned.zip'
            names.update({unsigned, unsigned + '.sha256'})
        if any(a['name'] in names for a in assets):
            return 'target_asset_already_exists'
        if item['tag'] not in self.commits:
            commit = self.api.request(f"{self.api.root}/commits/{item['tag']}")
            if not isinstance(commit, dict) or not isinstance(commit.get('sha'), str):
                raise ValueError('Malformed release commit response; nothing may be claimed')
            self.commits[item['tag']] = commit['sha']
        if self.commits[item['tag']] != item['sha']:
            return 'release_tag_source_changed'
        return None
