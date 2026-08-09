#!/usr/bin/env python3
"""Build and compare schema v1 evidence from an official GitHub run."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Mapping
from urllib.parse import urlparse


EVIDENCE_SCHEMA_VERSION: Final[int] = 1
BASIC_JOB_NAME: Final[str] = "basic-tests"
BASIC_STEP_NAME: Final[str] = "Run deterministic basic tests"


def parse_utc_timestamp(value: object, field_name: str) -> datetime:
    """Parse a timezone-aware ISO timestamp from the official run payload."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty ISO 8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)

def calculate_source_duration_seconds(created_at: str, updated_at: str) -> float:
    """Calculate trigger-to-terminal duration, including runner queue time."""
    created = parse_utc_timestamp(created_at, "created_at")
    updated = parse_utc_timestamp(updated_at, "updated_at")
    duration = (updated - created).total_seconds()
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("source updated_at must not precede created_at")
    return duration

def _required_run_metadata(source_run: Mapping[str, object]) -> dict[str, object]:
    run_id = source_run.get("id")
    attempt = source_run.get("run_attempt")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise ValueError("source run id must be a positive integer")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("source run_attempt must be a positive integer")
    if source_run.get("status") != "completed":
        raise ValueError("source run must be terminal with status completed")
    if source_run.get("name") != "ci-infra-canary":
        raise ValueError("source run workflow name must be ci-infra-canary")
    trigger = source_run.get("event")
    if trigger not in {"schedule", "workflow_dispatch"}:
        raise ValueError("source run event must be schedule or workflow_dispatch")
    run_url = source_run.get("html_url")
    if not isinstance(run_url, str) or urlparse(run_url).scheme not in {"http", "https"}:
        raise ValueError("source run html_url must be an http or https URL")
    head_sha = source_run.get("head_sha")
    if not isinstance(head_sha, str) or not head_sha.strip():
        raise ValueError("source run head_sha must be a non-empty string")
    created_at, updated_at = source_run.get("created_at"), source_run.get("updated_at")
    created, updated = parse_utc_timestamp(created_at, "created_at"), parse_utc_timestamp(updated_at, "updated_at")
    return {
        "run_id": run_id,
        "run_attempt": attempt,
        "trigger": trigger,
        "run_url": run_url,
        "head_sha": head_sha,
        "created_at": created.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "updated_at": updated.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "duration_seconds": calculate_source_duration_seconds(created_at, updated_at),
    }

def _jobs_list(jobs_payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    jobs = jobs_payload.get("jobs")
    if not isinstance(jobs, list) or any(not isinstance(job, Mapping) for job in jobs):
        raise ValueError("jobs payload must contain a list of job objects")
    return jobs

def extract_basic_step_outcome(source_run: Mapping[str, object], jobs_payload: Mapping[str, object]) -> tuple[bool, str, str, str]:
    """Read the exact basic job/step conclusion; missing execution stays UNKNOWN."""
    jobs = [job for job in _jobs_list(jobs_payload) if job.get("name") == BASIC_JOB_NAME]
    if len(jobs) != 1:
        return False, "unavailable", "basic_tests", "basic_job_not_found"
    steps = jobs[0].get("steps")
    if not isinstance(steps, list) or any(not isinstance(step, Mapping) for step in steps):
        return False, "unavailable", "basic_tests", "basic_step_not_found"
    matching = [step for step in steps if step.get("name") == BASIC_STEP_NAME]
    if len(matching) != 1:
        return False, "unavailable", "basic_tests", "basic_step_not_found"
    conclusion, job_conclusion = matching[0].get("conclusion"), jobs[0].get("conclusion")
    if conclusion == "success":
        if source_run.get("conclusion") == "success" and job_conclusion == "success":
            return True, "success", "basic_tests", "passed"
        failure_code = "source_run_failure" if source_run.get("conclusion") == "failure" else "basic_job_failure" if job_conclusion == "failure" else None
        return (True, "failure", "basic_tests", failure_code) if failure_code else (False, "unavailable", "basic_tests", "terminal_status_not_success")
    if conclusion == "failure":
        return True, "failure", "basic_tests", "test_failure"
    return False, "unavailable", "basic_tests", f"basic_step_{conclusion or 'not_executed'}"

def build_readiness_evidence(
    *, source_run: Mapping[str, object], jobs_payload: Mapping[str, object], observed_at: str
) -> dict[str, object]:
    """Build evidence from official run/job terminal facts, with Gate explicitly UNKNOWN."""
    metadata = _required_run_metadata(source_run)
    observed = parse_utc_timestamp(observed_at, "observed_at")
    proven, outcome, cause_domain, cause_code = extract_basic_step_outcome(source_run, jobs_payload)
    common = {
        **metadata,
        "started_at": metadata["created_at"],
        "completed_at": metadata["updated_at"],
    }
    basic_lane = {
        **common,
        "execution_proven": proven,
        "outcome": outcome,
        "detail": f"{BASIC_JOB_NAME}/{BASIC_STEP_NAME}: {cause_code}",
        "cause_domain": cause_domain,
        "cause_code": cause_code,
    }
    gate_lane = {
        **common,
        "execution_proven": False,
        "outcome": "unavailable",
        "detail": "Gate primary has no scheduled or no-PR entry; review was not executed",
        "cause_domain": "gate_review",
        "cause_code": "no_pr_entry",
        "review_executed": False,
        "verdict": "unavailable",
        "audit_identity": None,
    }
    return {"schema_version": EVIDENCE_SCHEMA_VERSION, "observed_at": observed.isoformat(timespec="seconds").replace("+00:00", "Z"), "source_run_id": metadata["run_id"], "lanes": {"basic_tests": basic_lane, "gate_review": gate_lane}}

def _read_json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot parse JSON evidence: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON evidence must be an object: {path}")
    return value


def evidence_identity(evidence: Mapping[str, object]) -> tuple[int, int]:
    """Extract the canonical source run tuple used to guard mutable latest."""
    lanes = evidence.get("lanes")
    basic = lanes.get("basic_tests") if isinstance(lanes, Mapping) else None
    run_id = basic.get("run_id") if isinstance(basic, Mapping) else None
    attempt = basic.get("run_attempt") if isinstance(basic, Mapping) else None
    if evidence.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        raise ValueError("existing evidence schema_version is not 1")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id < 1:
        raise ValueError("existing evidence basic_tests.run_id is invalid")
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise ValueError("existing evidence basic_tests.run_attempt is invalid")
    return run_id, attempt


def stable_asset_action(existing: Mapping[str, object], candidate: Mapping[str, object]) -> str:
    """Return publish only for a strictly newer source run tuple."""
    return "publish" if evidence_identity(existing) < evidence_identity(candidate) else "skip"


def write_readiness_evidence(output_path: Path, evidence: Mapping[str, object]) -> None:
    """Write canonical sorted JSON shared by per-run and stable publication."""
    output_path.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "source-run-json", "jobs-json", "compare-existing", "candidate"):
        parser.add_argument(f"--{name}", dest=name.replace("-", "_"), type=Path)
    parser.add_argument("--observed-at")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    try:
        if args.compare_existing:
            if not args.candidate:
                raise ValueError("--candidate is required with --compare-existing")
            print(stable_asset_action(_read_json_object(args.compare_existing), _read_json_object(args.candidate)))
            return 0
        if any(value is None for value in (args.output, args.source_run_json, args.jobs_json, args.observed_at)):
            raise ValueError("--output, --source-run-json, --jobs-json and --observed-at are required")
        write_readiness_evidence(args.output, build_readiness_evidence(source_run=_read_json_object(args.source_run_json), jobs_payload=_read_json_object(args.jobs_json), observed_at=args.observed_at))
        return 0
    except ValueError as exc:
        raise SystemExit(f"invalid readiness evidence: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
