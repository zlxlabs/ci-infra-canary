#!/usr/bin/env python3
"""Build the schema v1 basic-tests readiness evidence consumed by M3."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Final
from urllib.parse import urlparse


EVIDENCE_SCHEMA_VERSION: Final[int] = 1
STABLE_RELEASE_TAG: Final[str] = "ci-readiness-evidence-v1"
STABLE_RELEASE_ASSET: Final[str] = "ci-readiness-evidence-v1.json"
STABLE_RELEASE_URL: Final[str] = (
    "https://github.com/zlxlabs/ci-infra-canary/releases/download/"
    "ci-readiness-evidence-v1/ci-readiness-evidence-v1.json"
)


def parse_utc_timestamp(value: str, field_name: str) -> datetime:
    """Parse an ISO 8601 timestamp and require an explicit timezone."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty ISO 8601 string")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def format_utc_timestamp(value: datetime) -> str:
    """Format evidence timestamps as stable UTC strings with a trailing Z."""
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def calculate_duration_seconds(started_at: str, completed_at: str) -> float:
    """Calculate a finite non-negative duration from actual UTC timestamps."""
    started = parse_utc_timestamp(started_at, "basic_started_at")
    completed = parse_utc_timestamp(completed_at, "basic_completed_at")
    duration = (completed - started).total_seconds()
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("basic test completed_at must not precede started_at")
    return duration


def validate_run_metadata(run_url: str, head_sha: str, run_attempt: int, trigger: str) -> None:
    """Validate the GitHub run identity and exact schedule/manual trigger name."""
    if not isinstance(run_url, str) or not run_url.strip():
        raise ValueError("run_url must be a non-empty URL")
    parsed_url = urlparse(run_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("run_url must be an http or https URL")
    if not isinstance(head_sha, str) or not head_sha.strip():
        raise ValueError("head_sha must be a non-empty string")
    if isinstance(run_attempt, bool) or not isinstance(run_attempt, int) or run_attempt < 1:
        raise ValueError("run_attempt must be a positive integer")
    if trigger not in {"schedule", "workflow_dispatch"}:
        raise ValueError("trigger must be schedule or workflow_dispatch")


def build_readiness_evidence(
    *,
    observed_at: str,
    basic_started_at: str,
    basic_completed_at: str,
    basic_outcome: str,
    run_url: str,
    head_sha: str,
    run_attempt: int,
    trigger: str,
    basic_detail: str,
) -> dict[str, object]:
    """Build one basic execution record while keeping the Gate lane honestly UNKNOWN."""
    observed = parse_utc_timestamp(observed_at, "observed_at")
    started = parse_utc_timestamp(basic_started_at, "basic_started_at")
    completed = parse_utc_timestamp(basic_completed_at, "basic_completed_at")
    duration_seconds = calculate_duration_seconds(basic_started_at, basic_completed_at)
    if completed > observed:
        raise ValueError("observed_at must be at or after basic_completed_at")
    validate_run_metadata(run_url, head_sha, run_attempt, trigger)
    if basic_outcome not in {"success", "failure"}:
        raise ValueError("basic_outcome must be success or failure")
    if not isinstance(basic_detail, str) or not basic_detail.strip():
        raise ValueError("basic_detail must be a non-empty string")

    basic_lane = {
        "execution_proven": True,
        "outcome": basic_outcome,
        "started_at": format_utc_timestamp(started),
        "completed_at": format_utc_timestamp(completed),
        "duration_seconds": duration_seconds,
        "run_url": run_url,
        "head_sha": head_sha,
        "run_attempt": run_attempt,
        "trigger": trigger,
        "cause_domain": "basic_tests",
        "cause_code": "passed" if basic_outcome == "success" else "test_failure",
        "detail": basic_detail,
    }
    gate_lane = {
        "execution_proven": False,
        "outcome": "unavailable",
        "started_at": None,
        "completed_at": None,
        "duration_seconds": 0.0,
        "run_url": run_url,
        "head_sha": head_sha,
        "run_attempt": run_attempt,
        "trigger": trigger,
        "cause_domain": "gate_review",
        "cause_code": "no_pr_entry",
        "detail": "Gate primary has no scheduled or no-PR entry; review was not executed",
        "review_executed": False,
        "verdict": "unavailable",
        "audit_identity": None,
    }
    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "observed_at": format_utc_timestamp(observed),
        "lanes": {"basic_tests": basic_lane, "gate_review": gate_lane},
    }


def write_readiness_evidence(output_path: Path, evidence: dict[str, object]) -> None:
    """Write deterministic sorted JSON so artifact and release bytes can be compared."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    output_path.write_text(serialized + "\n", encoding="utf-8")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--basic-started-at", required=True)
    parser.add_argument("--basic-completed-at", required=True)
    parser.add_argument("--basic-outcome", choices=("success", "failure"), required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--trigger", choices=("schedule", "workflow_dispatch"), required=True)
    parser.add_argument("--basic-detail", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    try:
        evidence = build_readiness_evidence(
            observed_at=args.observed_at,
            basic_started_at=args.basic_started_at,
            basic_completed_at=args.basic_completed_at,
            basic_outcome=args.basic_outcome,
            run_url=args.run_url,
            head_sha=args.head_sha,
            run_attempt=args.run_attempt,
            trigger=args.trigger,
            basic_detail=args.basic_detail,
        )
    except ValueError as exc:
        raise SystemExit(f"invalid readiness evidence: {exc}") from exc
    write_readiness_evidence(args.output, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
