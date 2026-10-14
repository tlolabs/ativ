"""Regression checks for the consolidated CI failure tracker."""

import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import report_ci_failures


class CurrentRunFailuresTests(unittest.TestCase):
    def setUp(self):
        self.workflow = sorted(report_ci_failures.MONITORED_WORKFLOWS)[0]

    def run_record(self, branch, status, conclusion, created):
        return {
            "databaseId": 123,
            "workflowName": self.workflow,
            "status": status,
            "conclusion": conclusion,
            "createdAt": created,
            "headBranch": branch,
            "headSha": "abc123",
            "url": "https://github.com/example/repo/actions/runs/123",
            "event": "push",
        }

    def test_pending_successor_and_deleted_branch_do_not_report_old_failures(self):
        runs = [
            self.run_record("main", "completed", "failure", "2026-10-11T10:00:00Z"),
            self.run_record("main", "queued", "", "2026-10-11T11:00:00Z"),
            self.run_record("deleted-branch", "completed", "failure", "2026-10-11T12:00:00Z"),
        ]
        runs[-1]["event"] = "pull_request"

        def fake_gh(*args, **_kwargs):
            self.assertEqual(args[:2], ("run", "list"))
            return SimpleNamespace(stdout=json.dumps(runs))

        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "example/repo"}), \
             patch.object(report_ci_failures, "fetch_json", side_effect=lambda path: [{"name": "main"}] if "/branches?" in path else []), \
             patch.object(report_ci_failures, "gh", side_effect=fake_gh):
            self.assertEqual(report_ci_failures.current_run_failures(), [])

    def test_current_failed_job_remains_visible(self):
        runs = [
            self.run_record("main", "completed", "failure", "2026-10-11T12:00:00Z"),
            self.run_record("open-pr", "completed", "failure", "2026-10-11T12:00:00Z"),
        ]
        runs[-1]["event"] = "pull_request"

        def fake_gh(*args, **_kwargs):
            if args[:2] == ("run", "list"):
                return SimpleNamespace(stdout=json.dumps(runs))
            self.assertEqual(args[:2], ("run", "view"))
            return SimpleNamespace(stdout=json.dumps({"jobs": [{"name": "Linux arm64", "conclusion": "failure"}]}))

        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "example/repo"}), \
             patch.object(report_ci_failures, "fetch_json", side_effect=lambda path: [{"name": "main"}] if "/branches?" in path else [{"head": {"ref": "open-pr"}}] if "/pulls?" in path else []), \
             patch.object(report_ci_failures, "gh", side_effect=fake_gh):
            failures = report_ci_failures.current_run_failures()
        self.assertEqual({item["branch"] for item in failures}, {"main", "open-pr"})
        self.assertTrue(all(item["jobs"] == "Linux arm64" for item in failures))


    def test_publish_independently_verified_native_platforms_monitored(self):
        runs = [
            {
                "databaseId": 456,
                "workflowName": "Publish independently verified native platforms",
                "status": "completed",
                "conclusion": "failure",
                "createdAt": "2026-10-14T10:00:00Z",
                "headBranch": "main",
                "headSha": "def456",
                "url": "https://github.com/example/repo/actions/runs/456",
                "event": "push",
            }
        ]

        def fake_gh(*args, **_kwargs):
            if args[:2] == ("run", "list"):
                return SimpleNamespace(stdout=json.dumps(runs))
            self.assertEqual(args[:2], ("run", "view"))
            return SimpleNamespace(stdout=json.dumps({"jobs": [{"name": "Publish Linux", "conclusion": "failure"}]}))

        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "example/repo"}), \
             patch.object(report_ci_failures, "fetch_json", side_effect=lambda path: [{"name": "main"}] if "/branches?" in path else []), \
             patch.object(report_ci_failures, "gh", side_effect=fake_gh):
            failures = report_ci_failures.current_run_failures()
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["workflow"], "Publish independently verified native platforms")
        self.assertEqual(failures[0]["jobs"], "Publish Linux")

    def test_diagnostic_step_failure_detected_in_successful_run(self):
        runs = [
            {
                "databaseId": 789,
                "workflowName": "Native build, test, and package",
                "status": "completed",
                "conclusion": "success",
                "createdAt": "2026-10-14T12:00:00Z",
                "headBranch": "main",
                "headSha": "789abc",
                "url": "https://github.com/example/repo/actions/runs/789",
                "event": "push",
            }
        ]

        jobs_data = {
            "jobs": [
                {
                    "name": "Linux arm64",
                    "status": "completed",
                    "conclusion": "success",
                    "steps": [
                        {"name": "Set up toolchain", "status": "completed", "conclusion": "success"},
                        {
                            "name": "Inspect Qt accessibility semantics and compact layout (informational)",
                            "status": "completed",
                            "conclusion": "failure",
                        },
                    ],
                }
            ]
        }

        def fake_gh(*args, **_kwargs):
            if args[:2] == ("run", "list"):
                return SimpleNamespace(stdout=json.dumps(runs))
            self.assertEqual(args[:2], ("run", "view"))
            return SimpleNamespace(stdout=json.dumps(jobs_data))

        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "example/repo"}), \
             patch.object(report_ci_failures, "fetch_json", side_effect=lambda path: [{"name": "main"}] if "/branches?" in path else []), \
             patch.object(report_ci_failures, "gh", side_effect=fake_gh):
            failures = report_ci_failures.current_run_failures()
        self.assertEqual(len(failures), 1)
        self.assertIn("diagnostic", failures[0]["key"])
        self.assertIn("accessibility semantics", failures[0]["jobs"])


class AdditionalReporterTests(unittest.TestCase):
    def test_fetch_json_pagination_flattens_slurped_pages(self):
        pages = [[{"name": "branch-1"}], [{"name": "branch-2"}]]
        fake_res = SimpleNamespace(stdout=json.dumps(pages))
        with patch.object(report_ci_failures, "gh", return_value=fake_res) as mock_gh:
            result = report_ci_failures.fetch_json("repos/example/repo/branches?per_page=100")
            self.assertEqual(result, [{"name": "branch-1"}, {"name": "branch-2"}])
            mock_gh.assert_called_once_with("api", "--paginate", "--slurp", "repos/example/repo/branches?per_page=100")

    def test_security_findings_handles_unavailable_and_error_dict(self):
        error_response = {"message": "Dependabot alerts are disabled for this repository"}

        def fake_fetch(path):
            if "dependabot" in path:
                return error_response
            return []

        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "example/repo"}), \
             patch.object(report_ci_failures, "fetch_json", side_effect=fake_fetch):
            findings = report_ci_failures.security_findings()
        self.assertEqual(len(findings), 1)
        self.assertIn("alert status unavailable: Dependabot alerts are disabled", findings[0]["title"])

    def test_render_preserves_persistent_and_resolved_history(self):
        failures = [
            {
                "key": "wf|main",
                "workflow": "wf",
                "branch": "main",
                "sha": "123456789012",
                "jobs": "job1",
                "url": "https://example.com/run",
            },
            {
                "key": "wf|main|diagnostic|job2|stepA",
                "workflow": "wf",
                "branch": "main",
                "sha": "123456789012",
                "jobs": "job2 (diagnostic step: stepA)",
                "url": "https://example.com/run",
            },
        ]
        previous = {"wf|main", "old_wf|main"}
        rendered, current = report_ci_failures.render(failures, previous, None)
        self.assertIn("Persistent — wf / main", rendered)
        self.assertIn("New — wf / main", rendered)
        self.assertIn("- **Resolved** — `old_wf|main`", rendered)
        self.assertEqual(current, {"wf|main", "wf|main|diagnostic|job2|stepA"})


if __name__ == "__main__":
    unittest.main()
