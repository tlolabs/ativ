"""Focused checks for independent native publication eligibility."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import publish_native_platforms as publisher


class NativePublisherTests(unittest.TestCase):
    def setUp(self):
        self.run = {
            "id": 123,
            "run_number": 118,
            "event": "push",
            "path": publisher.WORKFLOW,
            "head_branch": "main",
            "head_sha": "a" * 40,
            "repository": {"full_name": publisher.REPO},
            "head_repository": {"full_name": publisher.REPO},
        }

    def test_development_is_distinct_from_annotated_stable_release(self):
        with patch.object(publisher, "source_version", return_value="0.2.6"):
            self.assertEqual(publisher.release_identity(self.run),
                             ("0.2.6-dev.118", "development-0.2.6-dev.118", False))
            stable = dict(self.run, head_branch="v0.2.6")
            self.assertEqual(publisher.release_identity(stable),
                             ("0.2.6", "v0.2.6", True))
            for change in ({"head_branch": "feature"},
                           {"head_repository": {"full_name": "someone/ativ"}},
                           {"event": "pull_request"}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    publisher.release_identity(dict(self.run, **change))

    def test_target_needs_functional_steps_and_upload(self):
        required = publisher.COMMON_STEPS | set(publisher.TARGETS["macos-arm64"][3])
        steps = [{"name": name, "conclusion": "success"} for name in required]
        steps.append({"name": "Run actions/upload-artifact@pinned", "conclusion": "success"})
        job = {"name": "macOS arm64", "status": "completed",
               "conclusion": "success", "steps": steps}
        self.assertEqual(publisher.native_job([job], "macos-arm64"), job)
        job["steps"] = [step for step in steps if step["name"] != "Validate packaged application and startup"]
        with self.assertRaisesRegex(ValueError, "lacks native tests"):
            publisher.native_job([job], "macos-arm64")

    def test_artifact_digest_and_host_report_bind_exact_package(self):
        version = "0.2.6-dev.118"
        package_name = f"ATIV-{version}-macos-arm64.zip"
        package_bytes = b"synthetic native application"
        evidence = {
            "schema": 1, "scope": "native_host_packaging", "status": "passed",
            "application_repository": publisher.REPO,
            "application_revision": self.run["head_sha"],
            "application_version": version,
            "target": "macos-arm64", "native_target": "macos-arm64",
            "evidence_origin": {
                "repository": publisher.REPO, "revision": self.run["head_sha"],
                "event": "push", "run_id": str(self.run["id"]),
            },
            "checks": {name: {"status": "passed"} for name in
                       ("packaging", "launch", "media", "lifecycle")},
            "packages": [{
                "filename": package_name,
                "sha256": hashlib.sha256(package_bytes).hexdigest(),
                "size": len(package_bytes),
            }],
        }
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            original = root / "original.zip"
            with zipfile.ZipFile(original, "w") as archive:
                archive.writestr(package_name, package_bytes)
                archive.writestr("host-macos-arm64.json", json.dumps(evidence))
            artifact = {
                "id": 9, "digest": "sha256:" + publisher.sha256(original),
            }

            def download(_args, stdout, check):
                stdout.write(original.read_bytes())

            output = root / "output"
            output.mkdir()
            with patch.object(publisher.subprocess, "run", side_effect=download), \
                    patch.object(publisher, "verify_package", return_value="macos-arm64"):
                package, report, checksum = publisher.read_candidate(
                    artifact, self.run, "macos-arm64", version, output)
                self.assertEqual(package.read_bytes(), package_bytes)
                self.assertEqual(json.loads(report.read_text())["application_revision"],
                                 self.run["head_sha"])
                self.assertIn(hashlib.sha256(package_bytes).hexdigest(),
                              checksum.read_text())
                artifact["digest"] = "sha256:" + "0" * 64
                with self.assertRaisesRegex(ValueError, "archive digest mismatch"):
                    publisher.read_candidate(artifact, self.run, "macos-arm64",
                                             version, output)


if __name__ == "__main__":
    unittest.main()
