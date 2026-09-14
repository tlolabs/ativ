#!/usr/bin/env python3
"""Validate a Developer ID identity and install ATIV's GitHub signing secrets.

Run interactively on macOS. Passwords are prompted without echo; subprocess
arguments/output containing credentials are never logged by this script.
"""
import argparse
import base64
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import tempfile

REPOSITORY = 'tlolabs/ativ'
SECRET_NAMES = (
    'MACOS_CERTIFICATE_BASE64', 'MACOS_CERTIFICATE_PASSWORD',
    'MACOS_SIGNING_IDENTITY', 'MACOS_NOTARY_APPLE_ID',
    'MACOS_NOTARY_PASSWORD', 'MACOS_NOTARY_TEAM_ID',
)


def run(args, *, data=None, purpose):
    result = subprocess.run(args, input=data, capture_output=True)
    if result.returncode:
        # CalledProcessError would include password-bearing command arguments.
        raise RuntimeError(f'{purpose} failed. No credential values were logged.')
    return result.stdout.decode()


def developer_identity(output):
    identities = re.findall(r'"(Developer ID Application: [^"\n]+ \(([A-Z0-9]{10})\))"', output)
    if len(identities) != 1:
        raise ValueError('The .p12 must contain exactly one valid Developer ID Application identity, including its private key.')
    return identities[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('certificate', type=Path, help='Developer ID Application .p12 including private key')
    parser.add_argument('--replace', action='store_true', help='Explicitly replace existing ATIV macOS signing secrets')
    args = parser.parse_args()
    if sys.platform != 'darwin' or not sys.stdin.isatty():
        parser.error('Run this command in an interactive macOS terminal.')
    certificate = args.certificate.expanduser().resolve(strict=True)
    if not 0 < certificate.stat().st_size < 32_000:
        parser.error('Expected a .p12 smaller than 32 KB (GitHub secret size limit).')
    existing = json.loads(run(['gh', 'secret', 'list', '--repo', REPOSITORY, '--json', 'name'], purpose='GitHub access check'))
    if not args.replace and any(item['name'] in SECRET_NAMES for item in existing):
        parser.error('Apple signing secrets already exist. Use --replace only for an intentional replacement or interrupted setup.')
    password = getpass.getpass('Certificate export password: ')
    if not password:
        parser.error('Use a password-protected .p12 export.')
    apple_id = input('Apple Developer account email: ').strip()
    if '@' not in apple_id:
        parser.error('Enter the Apple account email used for notarization.')
    notary_password = getpass.getpass('Apple app-specific password (not your account password): ')
    if not notary_password:
        parser.error('An app-specific password is required.')
    os.environ.setdefault('DEVELOPER_DIR', '/Applications/Xcode.app/Contents/Developer')
    old_search = shlex.split(run(['security', 'list-keychains', '-d', 'user'], purpose='Keychain search-list check'))
    with tempfile.TemporaryDirectory(prefix='ativ-signing-') as directory:
        keychain = str(Path(directory) / 'validation.keychain-db')
        keychain_password = secrets.token_urlsafe(32)
        try:
            run(['security', 'create-keychain', '-p', keychain_password, keychain], purpose='Temporary keychain creation')
            run(['security', 'unlock-keychain', '-p', keychain_password, keychain], purpose='Temporary keychain unlock')
            run(['security', 'import', str(certificate), '-P', password, '-t', 'cert', '-f', 'pkcs12', '-k', keychain, '-T', '/usr/bin/codesign'], purpose='Certificate and private-key import')
            output = run(['security', 'find-identity', '-v', '-p', 'codesigning', keychain], purpose='Signing identity validation')
            identity, team = developer_identity(output)
            print(f'Validated {identity}')
            run(['xcrun', 'notarytool', 'store-credentials', 'ativ-validation', '--apple-id', apple_id, '--team-id', team, '--password', notary_password, '--keychain', keychain, '--validate'], purpose='Apple notarization authentication')
            print('Apple notarization authentication passed. Uploading six secrets to tlolabs/ativ.')
            values = (base64.b64encode(certificate.read_bytes()), password.encode(), identity.encode(), apple_id.encode(), notary_password.encode(), team.encode())
            for name, value in zip(SECRET_NAMES, values):
                run(['gh', 'secret', 'set', name, '--repo', REPOSITORY], data=value, purpose=f'GitHub upload for {name}')
            configured = json.loads(run(['gh', 'secret', 'list', '--repo', REPOSITORY, '--json', 'name'], purpose='Secret-name readback'))
            if not set(SECRET_NAMES).issubset({item['name'] for item in configured}):
                raise RuntimeError('Secret-name verification failed; rerun with --replace after checking GitHub access.')
        finally:
            # Delete only this command's temporary keychain, preserving existing identities.
            subprocess.run(['security', 'delete-keychain', keychain], capture_output=True)
            run(['security', 'list-keychains', '-d', 'user', '-s', *old_search], purpose='Original keychain search-list restoration')
    print('All six macOS secrets configured. Run signed macOS validation before declaring the release ready.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError) as error:
        print(f'Setup stopped: {error}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nSetup cancelled.', file=sys.stderr)
        sys.exit(130)
