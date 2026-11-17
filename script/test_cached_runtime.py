#!/usr/bin/env python3
"""Offline cache validation regressions with real local hashes and metadata checks."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
from unittest.mock import patch

import core_runtime
import ffmpeg_runtime
import platform_runtime


class CachedRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = 'macos-arm64'
        pins = platform_runtime.obj(platform_runtime.PINS)
        legacy = platform_runtime.obj(platform_runtime.LEGACY)
        record, self.base = platform_runtime.record_for(self.target, pins)
        record = copy.deepcopy(record)
        self.directory = self.root / 'cache'
        self.runtime = self.directory / self.base
        self.runtime.mkdir(parents=True)

        def write_json(path, value):
            path.write_text(json.dumps(value, sort_keys=True) + '\n')

        def sha(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()

        source = self.directory / (self.base + '-sources.tar.gz')
        source.write_bytes(b'fixture corresponding source')
        (self.directory / (self.base + '.tar.gz')).write_bytes(b'fixture runtime archive')
        binaries = {}
        for name in ('ffmpeg', 'ffprobe'):
            path = self.runtime / name
            path.write_bytes(struct.pack('<II', 0xfeedfacf, 0x100000c) + name.encode())
            binaries[name] = sha(path)
        spec = {'source': {'revision': '1' * 40, 'version': record['version']},
                'recipe': record['recipe']}
        write_json(self.runtime / 'spec.json', spec)
        record['spec_sha256'] = sha(self.runtime / 'spec.json')
        self.build = {'target': self.target, 'core_revision': record['build_revision'],
                      'core_worktree_modified': False, 'source_revision': spec['source']['revision'],
                      'version': record['version'], 'recipe': record['recipe'],
                      'spec_sha256': record['spec_sha256']}
        write_json(self.runtime / 'build.json', self.build)
        write_json(self.runtime / 'validation.json', {'target': self.target, 'binary_sha256': binaries})
        write_json(self.runtime / 'repeat-build.json', {
            'status': 'passed', 'target': self.target, 'core_revision': record['build_revision'],
            'binary_sha256': {name: {'first': value, 'second': value} for name, value in binaries.items()}})
        write_json(self.runtime / 'SOURCE.json', {'sha256': sha(source)})
        write_json(self.runtime / 'source-provenance.json', {})
        (self.runtime / 'core-tests-passed.txt').write_text('passed\n')
        (self.runtime / 'SHA256SUMS').write_text(''.join(
            f'{sha(path)}  {path.name}\n' for path in sorted(self.runtime.iterdir())))
        record['checksums_sha256'] = sha(self.runtime / 'SHA256SUMS')
        record['binary_sha256'] = binaries
        archive = self.base + '.tar.gz'
        source_name = self.base + '-sources.tar.gz'
        write_json(self.directory / 'platform-release.json', {
            'schema': 1, 'kind': 'direct-download-platform', 'repository': platform_runtime.REPOSITORY,
            'target': self.target, **{name: record[name] for name in (
                'build_run', 'build_attempt', 'build_revision', 'native_job_id', 'artifact_id',
                'artifact_zip_sha256', 'spec_sha256')},
            'runtime_archive': archive, 'runtime_sha256': sha(self.directory / archive),
            'source_archive': source_name, 'source_sha256': sha(source)})
        (self.directory / (archive + '.sha256')).write_text(f'{sha(self.directory / archive)}  {archive}\n')
        (self.directory / 'SHA256SUMS').write_text(''.join(
            f'{sha(self.directory / name)}  {name}\n' for name in sorted(set(record['assets']) - {'SHA256SUMS'})))
        for name, asset in record['assets'].items():
            path = self.directory / name
            asset.update(size=path.stat().st_size, sha256=sha(path))
        write_json(self.directory / 'platform-verification.json', {
            'schema': 1, 'target': self.target, 'release_tag': record['release_tag'],
            'release_revision': record['release_revision'], 'runtime_sha256': record['assets'][archive]['sha256'],
            'version': record['version'], 'recipe': record['recipe']})
        pins['targets'][self.target] = record
        legacy['targets'][self.target]['spec_sha256'] = record['spec_sha256']
        pin_path, legacy_path = self.root / 'pins.json', self.root / 'legacy.json'
        write_json(pin_path, pins)
        write_json(legacy_path, legacy)
        for name, value in (('PINS', pin_path), ('LEGACY', legacy_path)):
            self.enterContext(patch.object(platform_runtime, name, value))
        self.origin = self.enterContext(patch.object(platform_runtime, 'verify_origin'))
        self.attestation = self.enterContext(patch.object(platform_runtime, 'verify_attestation'))

    def test_complete_cache_returns_build_and_hashes_each_binary_once(self):
        with patch.object(core_runtime, 'digest', wraps=core_runtime.digest) as digest:
            self.assertEqual(ffmpeg_runtime.verify(self.runtime, self.target), self.build)
        for name in ('ffmpeg', 'ffprobe'):
            self.assertEqual(sum(call.args[0] == self.runtime / name for call in digest.call_args_list), 1)
        self.origin.assert_called_once()
        self.attestation.assert_called_once()
        self.assertEqual(platform_runtime.verify_cached(self.target, self.directory), self.runtime)

    def test_corrupt_cached_payload_is_rejected(self):
        for path in (self.runtime / 'ffmpeg', self.runtime / 'build.json',
                     self.directory / (self.base + '-sources.tar.gz'),
                     self.directory / 'platform-release.json', self.directory / 'platform-verification.json'):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(b'{}')
                try:
                    with self.assertRaises(ValueError):
                        ffmpeg_runtime.verify(self.runtime, self.target)
                finally:
                    path.write_bytes(original)

    def test_attestation_failure_is_not_skipped(self):
        self.attestation.side_effect = ValueError('provider rejected attestation')
        with self.assertRaisesRegex(ValueError, 'provider rejected'):
            ffmpeg_runtime.verify(self.runtime, self.target)

    def test_alternate_directory_is_verified_in_addition_to_canonical_cache(self):
        alternate = self.directory / 'alternate-runtime'
        shutil.copytree(self.runtime, alternate)
        self.assertEqual(ffmpeg_runtime.verify(alternate, self.target), self.build)
        (alternate / 'ffprobe').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Executable hash mismatch'):
            ffmpeg_runtime.verify(alternate, self.target)

    def test_explicit_binary_override_is_verified(self):
        binary = self.root / 'overrides'
        binary.mkdir()
        for name in ('ffmpeg', 'ffprobe'):
            shutil.copy2(self.runtime / name, binary / name)
        self.assertEqual(ffmpeg_runtime.verify(self.runtime, self.target, binary=binary), self.build)
        (binary / 'ffmpeg').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Executable hash mismatch'):
            ffmpeg_runtime.verify(self.runtime, self.target, binary=binary)


if __name__ == '__main__':
    unittest.main()
