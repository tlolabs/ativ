#!/usr/bin/env python3
# SPDX-FileCopyrightText: Thomas Lothian
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression coverage for the frozen local Core source trust boundary."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from verify_core_source import ROOT, REVISION, verify


class CoreSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ativ-core-source-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT / 'vendor/avid-core', self.root / 'vendor/avid-core')
        shutil.copytree(ROOT / '.cargo', self.root / '.cargo')
        for name in ('Cargo.toml', 'Cargo.lock'):
            shutil.copy2(ROOT / name, self.root / name)
        self.crate = self.root / 'vendor/avid-core/avid-core-0.3.3'

    def test_complete_snapshot_needs_no_sibling_checkout_or_cargo(self):
        result = verify(self.root)
        self.assertEqual(result['revision'], REVISION)
        self.assertEqual(result['files_verified'], 71)

    def test_corrupted_source_is_rejected(self):
        with (self.crate / 'src/renderer.rs').open('ab') as stream:
            stream.write(b'\n// altered\n')
        with self.assertRaisesRegex(ValueError, 'source checksum mismatch: src/renderer.rs'):
            verify(self.root)

    def test_missing_source_is_rejected(self):
        (self.crate / 'src/storage.rs').unlink()
        with self.assertRaisesRegex(ValueError, 'source file set mismatch'):
            verify(self.root)

    def test_extra_source_is_rejected(self):
        (self.crate / 'src/extra.rs').write_text('// unexpected source\n')
        with self.assertRaisesRegex(ValueError, 'source file set mismatch'):
            verify(self.root)

    def test_linked_source_is_rejected(self):
        if not hasattr(__import__('os'), 'symlink'):
            self.skipTest('Platform has no symlink API')
        source = self.crate / 'src/storage.rs'
        body = source.read_bytes()
        outside = self.root / 'outside.rs'
        outside.write_bytes(body)
        source.unlink()
        try:
            source.symlink_to(outside)
        except OSError as error:
            self.skipTest('Symlinks unavailable: ' + str(error))
        with self.assertRaisesRegex(ValueError, 'Linked Core source entry'):
            verify(self.root)

    def test_cargo_checksum_manifest_must_match_source_manifest(self):
        path = self.crate / '.cargo-checksum.json'
        document = json.loads(path.read_text())
        document['files']['src/storage.rs'] = '0' * 64
        path.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, 'Cargo Core checksum manifest mismatch'):
            verify(self.root)

    def test_source_manifest_cannot_redefine_approved_snapshot(self):
        path = self.root / 'vendor/avid-core/source-manifest.json'
        document = json.loads(path.read_text())
        document['snapshot_sha256'] = '0' * 64
        path.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError, 'Core snapshot hash mismatch'):
            verify(self.root)

    def test_workspace_source_pin_cannot_drift_independently(self):
        path = self.root / 'Cargo.toml'
        path.write_text(path.read_text().replace(REVISION, 'a' * 40))
        with self.assertRaisesRegex(ValueError, 'Workspace Core source pin mismatch'):
            verify(self.root)

    def test_locked_source_pin_cannot_drift_independently(self):
        path = self.root / 'Cargo.lock'
        path.write_text(path.read_text().replace(REVISION, 'a' * 40))
        with self.assertRaisesRegex(ValueError, 'Locked Core source identity mismatch'):
            verify(self.root)

    def test_source_replacement_cannot_drift_independently(self):
        path = self.root / '.cargo/config.toml'
        path.write_text(path.read_text().replace(REVISION, 'a' * 40))
        with self.assertRaisesRegex(ValueError, 'Cargo Core source replacement identity mismatch'):
            verify(self.root)

    def test_source_replacement_must_use_checked_in_directory(self):
        path = self.root / '.cargo/config.toml'
        path.write_text(path.read_text().replace('directory = "vendor/avid-core"', 'directory = "../other"'))
        with self.assertRaisesRegex(ValueError, 'Cargo Core source replacement directory mismatch'):
            verify(self.root)

    def test_path_and_patch_overrides_are_rejected(self):
        path = self.root / '.cargo/config.toml'
        original = path.read_text()
        for override in ('paths = ["../other"]\n',
                         '[patch."https://github.com/tlolabs/avid-core.git"]\navid-core = { path = "../other" }\n',
                         '[replace]\n"avid-core:0.3.3" = { path = "../other" }\n'):
            with self.subTest(override=override):
                path.write_text(override + '\n' + original)
                with self.assertRaisesRegex(ValueError, 'bypass'):
                    verify(self.root)


if __name__ == '__main__':
    unittest.main()
