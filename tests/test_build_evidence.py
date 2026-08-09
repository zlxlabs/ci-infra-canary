import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_evidence.py"


class BuildEvidenceTests(unittest.TestCase):
    def test_builds_successful_basic_and_unknown_gate_lanes(self):
        from scripts.build_evidence import build_readiness_evidence

        evidence = build_readiness_evidence(
            observed_at="2026-08-09T00:00:30Z",
            basic_started_at="2026-08-09T00:00:00Z",
            basic_completed_at="2026-08-09T00:00:30Z",
            basic_outcome="success",
            run_url="https://github.com/zlxlabs/ci-infra-canary/actions/runs/42",
            head_sha="a" * 40,
            run_attempt=2,
            trigger="schedule",
            basic_detail="make test passed",
        )

        self.assertEqual(evidence["schema_version"], 1)
        self.assertEqual(evidence["observed_at"], "2026-08-09T00:00:30Z")
        basic = evidence["lanes"]["basic_tests"]
        self.assertTrue(basic["execution_proven"])
        self.assertEqual(basic["outcome"], "success")
        self.assertEqual(basic["duration_seconds"], 30.0)
        self.assertEqual(basic["run_attempt"], 2)
        self.assertEqual(basic["trigger"], "schedule")
        self.assertEqual(basic["detail"], "make test passed")

        gate = evidence["lanes"]["gate_review"]
        self.assertFalse(gate["execution_proven"])
        self.assertFalse(gate["review_executed"])
        self.assertEqual(gate["outcome"], "unavailable")
        self.assertEqual(gate["verdict"], "unavailable")
        self.assertIsNone(gate["audit_identity"])

    def test_failure_is_executed_and_has_non_negative_duration(self):
        from scripts.build_evidence import build_readiness_evidence

        evidence = build_readiness_evidence(
            observed_at="2026-08-09T00:01:00Z",
            basic_started_at="2026-08-09T00:00:59Z",
            basic_completed_at="2026-08-09T00:01:00Z",
            basic_outcome="failure",
            run_url="https://github.com/zlxlabs/ci-infra-canary/actions/runs/43",
            head_sha="b" * 40,
            run_attempt=1,
            trigger="workflow_dispatch",
            basic_detail="make test failed with exit code 1",
        )

        basic = evidence["lanes"]["basic_tests"]
        self.assertTrue(basic["execution_proven"])
        self.assertEqual(basic["outcome"], "failure")
        self.assertEqual(basic["cause_code"], "test_failure")
        self.assertGreaterEqual(basic["duration_seconds"], 0.0)

    def test_rejects_invalid_types_and_time_order(self):
        from scripts.build_evidence import build_readiness_evidence

        kwargs = dict(
            observed_at="2026-08-09T00:00:30Z",
            basic_started_at="2026-08-09T00:00:31Z",
            basic_completed_at="2026-08-09T00:00:30Z",
            basic_outcome="success",
            run_url="https://github.com/zlxlabs/ci-infra-canary/actions/runs/42",
            head_sha="a" * 40,
            run_attempt=2,
            trigger="schedule",
            basic_detail="ok",
        )
        with self.assertRaises(ValueError):
            build_readiness_evidence(**kwargs)

        kwargs["run_attempt"] = True
        with self.assertRaises(ValueError):
            build_readiness_evidence(**kwargs)

    def test_cli_writes_stable_sorted_json(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "evidence.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--output",
                    str(output_path),
                    "--observed-at",
                    "2026-08-09T00:00:30Z",
                    "--basic-started-at",
                    "2026-08-09T00:00:00Z",
                    "--basic-completed-at",
                    "2026-08-09T00:00:30Z",
                    "--basic-outcome",
                    "success",
                    "--run-url",
                    "https://github.com/zlxlabs/ci-infra-canary/actions/runs/42",
                    "--head-sha",
                    "a" * 40,
                    "--run-attempt",
                    "1",
                    "--trigger",
                    "schedule",
                    "--basic-detail",
                    "make test passed",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            raw = output_path.read_text()
            self.assertEqual(raw, output_path.read_text())
            payload = json.loads(raw)
            self.assertEqual(list(payload), sorted(payload))
            self.assertTrue(raw.endswith("\n"))

    def test_cli_rejects_malformed_timestamp(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--output",
                "/tmp/ci-infra-canary-invalid-evidence.json",
                "--observed-at",
                "not-a-time",
                "--basic-started-at",
                "2026-08-09T00:00:00Z",
                "--basic-completed-at",
                "2026-08-09T00:00:30Z",
                "--basic-outcome",
                "success",
                "--run-url",
                "https://github.com/zlxlabs/ci-infra-canary/actions/runs/42",
                "--head-sha",
                "a" * 40,
                "--run-attempt",
                "1",
                "--trigger",
                "schedule",
                "--basic-detail",
                "ok",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
