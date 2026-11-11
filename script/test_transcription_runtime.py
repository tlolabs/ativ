#!/usr/bin/env python3
"""Offline source-identity and optional-helper packaging regressions."""
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest import mock

import transcription_runtime as runtime


class TranscriptionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_pinned_release_archive_acquires_and_revalidates_every_file(self):
        destination = self.root / 'reviewed'
        self.assertEqual(runtime.acquire(destination=destination), destination)
        self.assertEqual(runtime.acquire(destination=destination), destination)
        (destination / 'apple/AVIDTranscription/Package.swift').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            runtime.acquire(destination=destination)

    def test_corrupt_archive_never_publishes_source(self):
        vendor = self.root / 'vendor'
        vendor.mkdir()
        shutil.copy2(runtime.VENDOR / runtime.MANIFEST, vendor / runtime.MANIFEST)
        (vendor / runtime.ARCHIVE).write_bytes(b'corrupt')
        destination = self.root / 'reviewed'
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            runtime.acquire(vendor=vendor, destination=destination)
        self.assertFalse(destination.exists())

    def test_source_release_identity_cannot_disagree_with_archive_pin(self):
        vendor = self.root / 'vendor'
        shutil.copytree(runtime.VENDOR, vendor)
        manifest = json.loads((vendor / runtime.MANIFEST).read_text())
        for key, value in (('source_revision', '0' * 40), ('source_release_tag', 'v0.3.2')):
            altered = {**manifest, key: value}
            (vendor / runtime.MANIFEST).write_text(json.dumps(altered))
            with self.assertRaisesRegex(ValueError, 'release identity mismatch'):
                runtime.acquire(vendor=vendor, destination=self.root / 'reviewed')
            self.assertFalse((self.root / 'reviewed').exists())

    def test_unexpected_source_in_existing_checkout_is_rejected(self):
        destination = self.root / 'reviewed'
        runtime.acquire(destination=destination)
        (destination / 'apple/AVIDTranscription/Sources/AVIDTranscription/Unreviewed.swift').write_text('// unreviewed')
        with self.assertRaisesRegex(ValueError, 'Unexpected file or directory'):
            runtime.acquire(destination=destination)

    def test_unknown_archive_member_cannot_escape_source(self):
        vendor = self.root / 'vendor'
        shutil.copytree(runtime.VENDOR, vendor)
        manifest = json.loads((vendor / runtime.MANIFEST).read_text())
        manifest['files'] = manifest['files'][1:]
        (vendor / runtime.MANIFEST).write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Unexpected archive member'):
            runtime.acquire(vendor=vendor, destination=self.root / 'reviewed')
        self.assertFalse((self.root / 'reviewed').exists())

    def test_intel_and_other_targets_cannot_include_apple_helper(self):
        app = self.root / 'ATIV.app'
        for target in ('macos-intel', 'windows-arm64', 'linux-arm64'):
            runtime.validate(app, target)
        (app / 'Contents/Helpers/ATIVTranscriptionHelper.app').mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'must not ship'):
            runtime.validate(app, 'macos-intel')

    def test_arm64_package_requires_helper_notices_and_manifest(self):
        with self.assertRaises(FileNotFoundError):
            runtime.validate(self.root / 'ATIV.app', 'macos-arm64')

    def test_macho_architecture_and_deployment_are_checked_without_tools(self):
        path = self.root / 'helper'
        header = struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 2, 1, 24, 0, 0)
        path.write_bytes(header + struct.pack('<IIIIII', 0x32, 24, 1, 0xe0000, 0x1b0000, 0))
        self.assertEqual(runtime.macho_deployment(path), (14, 0, 0))
        path.write_bytes(path.read_bytes().replace(struct.pack('<I', 0x100000c), struct.pack('<I', 0x1000007)))
        with self.assertRaisesRegex(ValueError, 'arm64'):
            runtime.macho_deployment(path)

    def test_integrity_seal_detects_resource_changes(self):
        directory = self.root / 'ATIV.app/Contents/Helpers/ATIVTranscriptionHelper.app'
        resources = directory / 'Contents/Resources'
        resources.mkdir(parents=True)
        (resources / 'models.json').write_text('original')
        runtime.seal(directory)
        manifest = json.loads((self.root / 'ATIV.app/Contents/Resources' / runtime.PACKAGE_MANIFEST).read_text())
        key = 'Contents/Resources/models.json'
        self.assertEqual(manifest['files'][key], runtime.sha256(resources / 'models.json'))
        (resources / 'models.json').write_text('changed')
        self.assertNotEqual(manifest['files'][key], runtime.sha256(resources / 'models.json'))

    def test_relocated_catalog_probe_resigns_only_copy_without_resealing_package(self):
        app = self.root / 'ATIV.app'
        directory = app / 'Contents/Helpers' / runtime.HELPER_BUNDLE
        resources = directory / 'Contents/Resources'
        catalog = resources / 'AVIDTranscription.bundle/models.json'
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps({'models': [{'displayName': 'Original'}] * 5}))
        licenses = resources / 'licenses'
        licenses.mkdir()
        for name in ('MODEL_NOTICES.md', 'THIRD_PARTY_NOTICES.md'):
            (licenses / name).write_text('notice')
        import plistlib
        (directory / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'LSMinimumSystemVersion': '14.0', 'CFBundleExecutable': runtime.HELPER_NAME}))
        helper = directory / 'Contents/MacOS' / runtime.HELPER_NAME
        helper.parent.mkdir()
        helper.write_bytes(b'fixture executable')
        runtime.seal(directory)
        manifest = app / 'Contents/Resources' / runtime.PACKAGE_MANIFEST
        before = {path: path.read_bytes() for path in app.rglob('*') if path.is_file()}
        signed = set()

        def run(command, **kwargs):
            if command[0] == '/usr/bin/codesign':
                target = Path(command[-1])
                self.assertFalse(target.is_relative_to(app))
                self.assertEqual(command[command.index('--sign') + 1], '-')
                signed.add(target)
                return runtime.subprocess.CompletedProcess(command, 0)
            relocated_helper = Path(command[0])
            relocated = relocated_helper.parent.parent.parent
            self.assertIn(relocated, signed, 'Modified copy must be signed before launch')
            models = json.loads((relocated / catalog.relative_to(directory)).read_text())['models']
            self.assertEqual(models[0]['displayName'], 'ATIV packaged-resource lookup check')
            return runtime.subprocess.CompletedProcess(command, 0,
                stdout=json.dumps({'event': 'result', 'models': models}) + '\n', stderr='')

        with mock.patch.object(runtime, 'macho_deployment', return_value=(14, 0, 0)), \
                mock.patch.object(runtime, 'validate_linkage'), \
                mock.patch.object(runtime.subprocess, 'run', side_effect=run), \
                mock.patch.object(runtime, 'seal', side_effect=AssertionError('Do not reseal a diagnostic copy')):
            runtime.validate(app, 'macos-arm64')
        self.assertEqual(before, {path: path.read_bytes() for path in app.rglob('*') if path.is_file()})
        self.assertEqual(json.loads(manifest.read_text())['files'][str(catalog.relative_to(directory))],
                         runtime.sha256(catalog))

    def test_external_runtime_and_developer_search_paths_are_rejected(self):
        helper = self.root / 'helper'

        def executable(kind, payload):
            helper.write_bytes(struct.pack('<IIIIIIII', 0xfeedfacf, 0x100000c, 0, 2, 1,
                                           len(payload) + 8, 0, 0) +
                               struct.pack('<II', kind, len(payload) + 8) + payload)

        executable(0xc, struct.pack('<IIII', 24, 0, 0, 0) + b'@rpath/missing.dylib\0')
        with self.assertRaisesRegex(ValueError, 'Unbundled helper runtime'):
            runtime.validate_linkage(helper, self.root)
        executable(0x8000001c, struct.pack('<I', 12) + b'/Applications/Xcode.app/Developer/runtime\0')
        with self.assertRaisesRegex(ValueError, 'Developer runtime search path'):
            runtime.validate_linkage(helper, self.root)


if __name__ == '__main__':
    unittest.main()
