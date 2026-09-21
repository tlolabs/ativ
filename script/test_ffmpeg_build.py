#!/usr/bin/env python3
"""Small regression tests for source trust boundaries and cache invalidation."""
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import ffmpeg_build as recipe


class SourceTests(unittest.TestCase):
    def test_corrupt_cached_source_is_rejected_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / 'source.tar.xz'
            archive.write_bytes(b'corrupt')
            with patch('urllib.request.urlopen') as network:
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    recipe.fetch('https://ffmpeg.org/releases/source.tar.xz', archive, '0' * 64)
                network.assert_not_called()

    def test_archive_traversal_and_links_are_rejected(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('/absolute', tarfile.REGTYPE), ('root/link', tarfile.SYMTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / 'source.tar'
                with tarfile.open(archive, 'w') as tar:
                    entry = tarfile.TarInfo(name)
                    entry.type = kind
                    tar.addfile(entry, io.BytesIO(b''))
                with self.assertRaisesRegex(ValueError, 'Unsafe source'):
                    recipe.extract(archive, root / 'unpacked')

    def test_cache_changes_with_recipe_target_and_compiler(self):
        with patch.object(recipe, 'recipe_digest', return_value='recipe-a'), patch.object(recipe, 'toolchain', return_value={'cc': 'compiler-a'}):
            original = recipe.fingerprint('linux-arm64')[0]
            self.assertNotEqual(original, recipe.fingerprint('linux-x86_64')[0])
            with patch.object(recipe, 'recipe_digest', return_value='recipe-b'):
                self.assertNotEqual(original, recipe.fingerprint('linux-arm64')[0])
            with patch.object(recipe, 'toolchain', return_value={'cc': 'compiler-b'}):
                self.assertNotEqual(original, recipe.fingerprint('linux-arm64')[0])

    def test_target_aliases_and_unknown_architectures(self):
        self.assertEqual(recipe.target_id('windows-x64'), 'windows-x86_64')
        self.assertEqual(recipe.target_id('linux-aarch64-appimage'), 'linux-arm64')
        with self.assertRaises(ValueError):
            recipe.target_id('linux-riscv64')


if __name__ == '__main__':
    unittest.main()
