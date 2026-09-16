#!/usr/bin/env python3
"""CI guard for Core-only production provisioning, immutable pins and bundled discovery."""
from pathlib import Path
import re
import tempfile
import unittest
import shutil

ROOT = Path(__file__).resolve().parents[1]
NORMAL = ['script/build_and_run.sh', 'script/package_macos.sh', 'script/package_linux.sh',
          'script/package_windows.ps1', '.github/workflows/native-release.yml']


def audit(root):
    revision = (root/'runtime/core-revision').read_text().strip()
    assert re.fullmatch('[0-9a-f]{40}', revision), 'Core must be pinned to an immutable commit'
    workflow = (root/'.github/workflows/native-release.yml').read_text()
    refs = re.findall(r'repository: tlolabs/avid-core\s+ref: (\S+)', workflow)
    assert len(refs) == 4 and set(refs) == {revision}, 'Every CI Core checkout must match runtime/core-revision'
    for name in NORMAL:
        text = (root/name).read_text()
        assert 'core_runtime.py' in text and 'provision' in text, f'{name}: missing Core provisioning'
        assert '--candidate' not in text, f'{name}: candidate runtime bypass in production'
        assert not re.search(r'FFMPEG_BIN|FFPROBE_BIN|FfmpegDirectory|fetch_ffmpeg|command -v ffmpeg', text), name
    for directory in ['script', '.github', 'crates', 'platform']:
        for path in (root/directory).rglob('*'):
            if not path.is_file() or path.suffix not in {'.sh', '.ps1', '.py', '.rs', '.yml', '.yaml', '.toml', '.cs', '.swift', '.c'}:
                continue
            if path.name == 'test_runtime_ownership.py':
                continue
            text = path.read_text()
            assert not re.search(r'BtbN|martin-riedl|evermeet|johnvansickle|ffbinaries', text, re.I), str(path)
            assert not re.search(r'https?://[^\s\"\']*(?:ffmpeg|ffprobe)[^\s\"\']*', text, re.I), str(path)
            assert not re.search(r'ffmpeg version [n0-9]|startswith\([\"\']9\.', text), str(path)
    discovery = (root/'crates/ativ-engine/src/media_tools.rs').read_text()
    assert '#[cfg(feature' not in discovery, 'Managed discovery must not depend on a build feature'
    assert 'from_managed_layout' in discovery and 'ffmpeg.is_none() && ffprobe.is_none()' in discovery
    assert not (root/'script/fetch_ffmpeg.sh').exists(), 'Legacy acquisition script remains'
    assert not (root/'script/verify_ffmpeg_distribution.py').exists(), 'Duplicate Core capability policy remains'


class OwnershipTests(unittest.TestCase):
    def test_repository(self):
        audit(ROOT)

    def test_blocks_production_bypass_and_mutable_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = NORMAL + ['runtime/core-revision', 'crates/ativ-engine/src/media_tools.rs']
            for name in names:
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT/name, path)
            audit(root)
            path = root/NORMAL[0]; original = path.read_text()
            path.write_text(original + '\n# --candidate\n')
            with self.assertRaises(AssertionError): audit(root)
            path.write_text(original)
            (root/'runtime/core-revision').write_text('main\n')
            with self.assertRaises(AssertionError): audit(root)

    def test_blocks_new_vendor_download(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in NORMAL + ['runtime/core-revision', 'crates/ativ-engine/src/media_tools.rs']:
                path = root/name; path.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(ROOT/name, path)
            (root/'script/new_downloader.sh').write_text('curl https://example.org/ffmpeg.zip\n')
            with self.assertRaises(AssertionError): audit(root)


if __name__ == '__main__':
    unittest.main()
