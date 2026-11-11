"""Local notarization policy regression checks; never invokes signing or Apple."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SIGN_VARIABLE='APPLE_SIGN_IDENTITY'
NOTARY_VARIABLE='APPLE_NOTARY_PROFILE'
FINAL_SIGN_VARIABLE='ATIV_SIGN_IDENTITY'
FINAL_NOTARY_VARIABLE='ATIV_NOTARY_PROFILE'
APP_VARIABLE='ATIV_APP_BUNDLE'
BUILD_SCRIPT='package_macos.sh'
BUILD_ARGS=('arm64',)
DEVELOPMENT_OPTION='--development'



class NotarizationDefaults(unittest.TestCase):
    def run_without_credentials(self, script, args=(), extra=None):
        env = {k: v for k, v in os.environ.items()
               if k not in ('APPLE_SIGN_IDENTITY', 'APPLE_NOTARY_PROFILE',
                            'ATIV_SIGN_IDENTITY', 'ATIV_NOTARY_PROFILE', 'ATIV_APP_BUNDLE',
                            'ENCAP_SIGN_IDENTITY', 'ENCAP_NOTARY_PROFILE')}
        env.update(extra or {})
        result = subprocess.run(['bash', str(ROOT / 'script' / script), *args],
                                env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        return result.stderr

    def test_default_distribution_requires_signing_before_build(self):
        self.assertIn(SIGN_VARIABLE, self.run_without_credentials(BUILD_SCRIPT, BUILD_ARGS))

    def test_default_distribution_requires_notary_before_build(self):
        self.assertIn(NOTARY_VARIABLE, self.run_without_credentials(
            BUILD_SCRIPT, BUILD_ARGS, {SIGN_VARIABLE: 'Developer ID Application: Test'}))

    def test_final_signer_requires_notary_before_reading_bundle(self):
        self.assertIn(FINAL_NOTARY_VARIABLE, self.run_without_credentials(
            'sign_macos_release.sh', extra={FINAL_SIGN_VARIABLE: 'Developer ID Application: Test',
                                            APP_VARIABLE: '/not/a/real/app'}))

    def test_invalid_profile_fails_before_build_or_bundle_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            stub = Path(directory)
            security = stub / 'security'
            security.write_text("#!/bin/sh\nprintf '%s\\n' 'Developer ID Application: Test'\n")
            security.chmod(0o755)
            xcrun = stub / 'xcrun'
            xcrun.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$NOTARY_TEST_LOG"\nexit 67\n')
            xcrun.chmod(0o755)
            log = stub / 'calls'
            for script, args, credentials in [
                (BUILD_SCRIPT, BUILD_ARGS, {SIGN_VARIABLE: 'Developer ID Application: Test',
                                           NOTARY_VARIABLE: 'missing-test-profile'}),
                ('sign_macos_release.sh', (), {FINAL_SIGN_VARIABLE: 'Developer ID Application: Test',
                                              FINAL_NOTARY_VARIABLE: 'missing-test-profile',
                                              APP_VARIABLE: '/not/a/real/app'})]:
                env = dict(os.environ, PATH=f'{stub}:{os.environ["PATH"]}',
                           NOTARY_TEST_LOG=str(log), **credentials)
                result = subprocess.run(['bash', str(ROOT / 'script' / script), *args],
                                        env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 67, result.stderr)
                self.assertEqual(log.read_text().strip(),
                                 'notarytool history --keychain-profile missing-test-profile --output-format json')

    def test_final_archive_is_validated_after_extraction(self):
        text = (ROOT / 'script/sign_macos_release.sh').read_text()
        self.assertIn("report.get('status') != 'Accepted'", text)
        self.assertIn('ditto -x -k "$ZIP" "$VERIFY"', text)
        self.assertIn('xcrun stapler validate "$VERIFY/', text)
        self.assertIn('spctl --assess --type execute --verbose=2 "$VERIFY/', text)
        self.assertNotIn('Signed only:', text)

    def test_explicit_development_archive_is_labeled(self):
        text = (ROOT / 'script' / BUILD_SCRIPT).read_text()
        self.assertIn(DEVELOPMENT_OPTION, text)
        self.assertIn('development-unnotarized', text)


if __name__ == '__main__':
    unittest.main()
