#!/usr/bin/env python3
# SPDX-FileCopyrightText: Thomas Lothian
# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated tampering tests for ATIV runtime integrity and trust boundaries."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class RuntimeTamperingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Look for local built engine and runtime bundle
        cls.macos_app = ROOT / "dist" / "ATIV.app"
        cls.engine_path = None
        cls.runtime_dir = None
        if cls.macos_app.exists():
            engine = cls.macos_app / "Contents" / "MacOS" / "ativ-engine"
            runtime = cls.macos_app / "Contents" / "Resources" / "FFmpeg"
            if engine.is_file() and runtime.is_dir():
                cls.engine_path = engine
                cls.runtime_dir = runtime

    def setUp(self):
        if not self.engine_path or not self.runtime_dir:
            self.skipTest("No packaged ativ-engine and FFmpeg runtime available for live tampering tests")
        self.temp_dir = tempfile.TemporaryDirectory(prefix="ativ-tamper-")
        self.test_root = Path(self.temp_dir.name)
        # Stage macOS app bundle structure:
        # Contents/MacOS/ativ-engine, ffmpeg, ffprobe
        # Contents/Resources/FFmpeg/*
        contents = self.test_root / "Contents"
        self.macos_dir = contents / "MacOS"
        self.macos_dir.mkdir(parents=True)
        self.ffmpeg_dir = contents / "Resources" / "FFmpeg"
        self.ffmpeg_dir.mkdir(parents=True)

        for binary in ("ativ-engine", "ffmpeg", "ffprobe"):
            src = self.engine_path.parent / binary
            if src.exists():
                shutil.copy2(src, self.macos_dir / binary)
                (self.macos_dir / binary).chmod(0o755)

        for item in self.runtime_dir.iterdir():
            if item.is_dir():
                shutil.copytree(item, self.ffmpeg_dir / item.name)
            else:
                shutil.copy2(item, self.ffmpeg_dir / item.name)

        self.engine_bin = self.macos_dir / "ativ-engine"

    def tearDown(self):
        if hasattr(self, "temp_dir"):
            self.temp_dir.cleanup()

    def run_check(self, extra_env=None):
        env = dict(os.environ)
        # Clear or point PATH to empty directory to ensure no PATH fallback
        env["PATH"] = ""
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(self.engine_bin), "check"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )

    def test_untampered_bundle_succeeds(self):
        res = self.run_check()
        self.assertEqual(res.returncode, 0, f"Untampered bundle failed check: {res.stderr}")
        data = json.loads(res.stdout.strip())
        self.assertEqual(data.get("event"), "tools")
        self.assertIn("ffmpeg", data)
        self.assertIn("ffprobe", data)

    def test_tampered_signed_payload_target_rejected(self):
        signed_payload_path = self.ffmpeg_dir / "signed-payload.json"
        data = json.loads(signed_payload_path.read_text())
        data["target"] = "tampered-target"
        signed_payload_path.write_text(json.dumps(data))

        res = self.run_check()
        self.assertNotEqual(res.returncode, 0, "Engine accepted tampered target in signed-payload.json")
        out = json.loads(res.stdout.strip())
        self.assertEqual(out.get("event"), "error")
        self.assertEqual(out.get("code"), "media_tools_unavailable")

    def test_tampered_signed_payload_binary_hash_rejected(self):
        signed_payload_path = self.ffmpeg_dir / "signed-payload.json"
        data = json.loads(signed_payload_path.read_text())
        data["signed_binary_sha256"]["ffmpeg"] = "0" * 64
        signed_payload_path.write_text(json.dumps(data))

        res = self.run_check()
        self.assertNotEqual(res.returncode, 0, "Engine accepted tampered binary hash in signed-payload.json")
        out = json.loads(res.stdout.strip())
        self.assertEqual(out.get("event"), "error")
        self.assertEqual(out.get("code"), "media_tools_unavailable")

    def test_tampered_signed_payload_archive_hash_rejected(self):
        signed_payload_path = self.ffmpeg_dir / "signed-payload.json"
        data = json.loads(signed_payload_path.read_text())
        data["original_runtime_archive_sha256"] = "f" * 64
        signed_payload_path.write_text(json.dumps(data))

        res = self.run_check()
        self.assertNotEqual(res.returncode, 0, "Engine accepted tampered archive hash in signed-payload.json")
        out = json.loads(res.stdout.strip())
        self.assertEqual(out.get("event"), "error")
        self.assertEqual(out.get("code"), "media_tools_unavailable")

    def test_tampered_sha256sums_rejected(self):
        sums_path = self.ffmpeg_dir / "SHA256SUMS"
        content = sums_path.read_text()
        # Corrupt one hash
        sums_path.write_text(content.replace(content[:64], "a" * 64))

        res = self.run_check()
        self.assertNotEqual(res.returncode, 0, "Engine accepted corrupted SHA256SUMS")
        out = json.loads(res.stdout.strip())
        self.assertEqual(out.get("event"), "error")
        self.assertEqual(out.get("code"), "media_tools_unavailable")

    def test_tampered_ffmpeg_executable_rejected(self):
        ffmpeg_bin = self.macos_dir / "ffmpeg"
        with ffmpeg_bin.open("r+b") as handle:
            handle.seek(1024)
            handle.write(b"TAMPERED_BYTES_HERE")

        res = self.run_check()
        self.assertNotEqual(res.returncode, 0, "Engine accepted modified ffmpeg binary")
        out = json.loads(res.stdout.strip())
        self.assertEqual(out.get("event"), "error")
        self.assertEqual(out.get("code"), "media_tools_unavailable")

    def test_unexpected_file_in_runtime_tree_rejected(self):
        injected = self.ffmpeg_dir / "unauthorized_payload.sh"
        injected.write_text("#!/bin/sh\necho evil\n")

        res = self.run_check()
        self.assertNotEqual(res.returncode, 0, "Engine accepted unexpected file in runtime directory")
        out = json.loads(res.stdout.strip())
        self.assertEqual(out.get("event"), "error")
        self.assertEqual(out.get("code"), "media_tools_unavailable")

    def test_tampered_ativ_runtime_provenance_rejected(self):
        prov_path = self.ffmpeg_dir / "ativ-runtime.json"
        data = json.loads(prov_path.read_text())
        data["owner"] = "Attacker"
        prov_path.write_text(json.dumps(data))

        res = self.run_check()
        self.assertNotEqual(res.returncode, 0, "Engine accepted tampered owner in ativ-runtime.json")
        out = json.loads(res.stdout.strip())
        self.assertEqual(out.get("event"), "error")
        self.assertEqual(out.get("code"), "media_tools_unavailable")


if __name__ == "__main__":
    unittest.main()
