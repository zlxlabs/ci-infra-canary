import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_evidence.py"


def source_run(*, run_id=42, attempt=2, created="2026-08-09T00:00:00Z", updated="2026-08-09T00:30:01Z"):
    return {
        "id": run_id,
        "name": "ci-infra-canary",
        "status": "completed",
        "event": "schedule",
        "created_at": created,
        "updated_at": updated,
        "run_attempt": attempt,
        "head_sha": "a" * 40,
        "html_url": f"https://github.com/zlxlabs/ci-infra-canary/actions/runs/{run_id}",
    }


def jobs_payload(conclusion=None, *, include_job=True, include_step=True):
    steps = [{"name": "Run deterministic basic tests", "conclusion": conclusion}] if include_step else []
    jobs = [{"name": "basic-tests", "conclusion": conclusion, "steps": steps}] if include_job else []
    return {"total_count": len(jobs), "jobs": jobs}


class BuildEvidenceTests(unittest.TestCase):
    def test_success_fixture_uses_official_queue_to_terminal_duration(self):
        from scripts.build_evidence import build_readiness_evidence

        evidence = build_readiness_evidence(
            source_run=source_run(), jobs_payload=jobs_payload("success"), observed_at="2026-08-09T00:31:00Z"
        )
        basic = evidence["lanes"]["basic_tests"]
        self.assertTrue(basic["execution_proven"])
        self.assertEqual(basic["outcome"], "success")
        self.assertEqual(basic["duration_seconds"], 1801.0)
        self.assertEqual(basic["started_at"], "2026-08-09T00:00:00Z")
        self.assertEqual(basic["completed_at"], "2026-08-09T00:30:01Z")
        self.assertEqual(basic["run_id"], 42)
        self.assertEqual(basic["run_attempt"], 2)

        gate = evidence["lanes"]["gate_review"]
        self.assertFalse(gate["execution_proven"])
        self.assertFalse(gate["review_executed"])
        self.assertEqual(gate["outcome"], "unavailable")
        self.assertEqual(gate["verdict"], "unavailable")
        self.assertEqual(gate["started_at"], basic["started_at"])
        self.assertEqual(gate["completed_at"], basic["completed_at"])
        self.assertIsNone(gate["audit_identity"])

    def test_failure_fixture_proves_basic_step_execution(self):
        from scripts.build_evidence import build_readiness_evidence

        evidence = build_readiness_evidence(
            source_run=source_run(run_id=43, attempt=1, updated="2026-08-09T00:00:01Z"),
            jobs_payload=jobs_payload("failure"),
            observed_at="2026-08-09T00:01:00Z",
        )
        basic = evidence["lanes"]["basic_tests"]
        self.assertTrue(basic["execution_proven"])
        self.assertEqual(basic["outcome"], "failure")
        self.assertEqual(basic["cause_code"], "test_failure")
        self.assertEqual(basic["duration_seconds"], 1.0)

    def test_not_executed_fixture_is_unavailable(self):
        from scripts.build_evidence import build_readiness_evidence

        for jobs in (jobs_payload("skipped"), jobs_payload("cancelled"), jobs_payload(None), jobs_payload(None, include_job=False)):
            evidence = build_readiness_evidence(
                source_run=source_run(), jobs_payload=jobs, observed_at="2026-08-09T00:31:00Z"
            )
            basic = evidence["lanes"]["basic_tests"]
            self.assertFalse(basic["execution_proven"])
            self.assertEqual(basic["outcome"], "unavailable")

    def test_rejects_non_terminal_source(self):
        from scripts.build_evidence import build_readiness_evidence

        run = source_run()
        run["status"] = "in_progress"
        with self.assertRaises(ValueError):
            build_readiness_evidence(source_run=run, jobs_payload=jobs_payload("success"), observed_at=run["updated_at"])

    def test_rejects_source_updated_before_created(self):
        from scripts.build_evidence import build_readiness_evidence

        run = source_run(created="2026-08-09T00:01:00Z", updated="2026-08-09T00:00:59Z")
        with self.assertRaises(ValueError):
            build_readiness_evidence(source_run=run, jobs_payload=jobs_payload("success"), observed_at="2026-08-09T00:02:00Z")

    def test_stable_asset_guard_accepts_only_newer_run_tuple(self):
        from scripts.build_evidence import build_readiness_evidence, stable_asset_action

        def build(run_id, attempt):
            return build_readiness_evidence(
                source_run=source_run(run_id=run_id, attempt=attempt),
                jobs_payload=jobs_payload("success"),
                observed_at="2026-08-09T00:31:00Z",
            )

        existing = build(100, 2)
        self.assertEqual(stable_asset_action(existing, build(101, 1)), "publish")
        self.assertEqual(stable_asset_action(existing, build(100, 2)), "skip")
        self.assertEqual(stable_asset_action(existing, build(100, 1)), "skip")
        self.assertEqual(stable_asset_action(existing, build(99, 9)), "skip")

    def test_cli_serialization_matches_canonical_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_path = root / "run.json"
            jobs_path = root / "jobs.json"
            output_one = root / "one.json"
            output_two = root / "two.json"
            run_path.write_text(json.dumps(source_run()), encoding="utf-8")
            jobs_path.write_text(json.dumps(jobs_payload("success")), encoding="utf-8")
            command = [
                sys.executable,
                str(SCRIPT),
                "--source-run-json",
                str(run_path),
                "--jobs-json",
                str(jobs_path),
                "--observed-at",
                "2026-08-09T00:31:00Z",
            ]
            for output in (output_one, output_two):
                result = subprocess.run(command + ["--output", str(output)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            raw = output_one.read_text()
            self.assertEqual(raw, output_two.read_text())
            payload = json.loads(raw)
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            self.assertEqual(raw, canonical)

    def test_cli_compares_a_valid_release_asset_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_path = root / "run.json"
            jobs_path = root / "jobs.json"
            candidate = root / "candidate.json"
            run_path.write_text(json.dumps(source_run()), encoding="utf-8")
            jobs_path.write_text(json.dumps(jobs_payload("success")), encoding="utf-8")
            build = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--source-run-json",
                    str(run_path),
                    "--jobs-json",
                    str(jobs_path),
                    "--observed-at",
                    "2026-08-09T00:31:00Z",
                    "--output",
                    str(candidate),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            compare = subprocess.run(
                [sys.executable, str(SCRIPT), "--compare-existing", str(candidate), "--candidate", str(candidate)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(compare.returncode, 0, compare.stderr)
            self.assertEqual(compare.stdout.strip(), "skip")


if __name__ == "__main__":
    unittest.main()
