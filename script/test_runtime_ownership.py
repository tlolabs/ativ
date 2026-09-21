#!/usr/bin/env python3
"""Guard ATIV-owned official sources, immutable pins and package-only discovery."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OwnershipTests(unittest.TestCase):
    def test_source_and_core_pins(self):
        spec = json.loads((ROOT / 'runtime/ffmpeg/dependency.json').read_text())
        self.assertRegex(spec['source']['version'], r'^\d+\.\d+(\.\d+)?$')
        self.assertEqual(spec['source']['url'], 'https://ffmpeg.org/releases/ffmpeg-' + spec['source']['version'] + '.tar.xz')
        for record in [spec['source'], *spec['external_libraries'].values()]:
            self.assertRegex(record['sha256'], r'^[0-9a-f]{64}$')
        revision = (ROOT / 'runtime/core-revision').read_text().strip()
        self.assertIn('rev = "' + revision + '"', (ROOT / 'Cargo.toml').read_text())
        self.assertEqual(len(spec['targets']), 6)

    def test_production_ownership(self):
        for name in ['build_and_run.sh', 'package_macos.sh', 'package_linux.sh', 'package_windows.ps1']:
            text = (ROOT / 'script' / name).read_text()
            self.assertIn('ffmpeg_runtime.py', text)
            self.assertIn('provision', text)
            self.assertNotIn('--candidate', text)
        for directory in ['script', '.github', 'crates', 'platform']:
            for path in (ROOT / directory).rglob('*'):
                if not path.is_file() or path.suffix not in {'.py', '.sh', '.ps1', '.rs', '.yml', '.toml'} or path == Path(__file__):
                    continue
                if any(part in {'target', '.build', 'bin', 'obj'} for part in path.parts):
                    continue
                text = path.read_text()
                self.assertNotRegex(text, r'BtbN|martin-riedl|evermeet|johnvansickle|ffbinaries|scripts/ffmpeg/acquire|from_managed_layout', str(path))
        discovery = (ROOT / 'crates/ativ-engine/src/media_tools.rs').read_text()
        self.assertIn('search_path: false', discovery)
        self.assertIn('DEPENDENCY.as_bytes()', discovery)


if __name__ == '__main__':
    unittest.main()
