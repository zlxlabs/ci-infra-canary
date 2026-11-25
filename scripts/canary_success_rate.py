#!/usr/bin/env python3
"""Print the canary success rate over the last N days.

usage: canary_success_rate.py <days>    (one of 1, 7, 30)

Reads the official Actions runs API through ``gh`` and prints one line:
``CANARY-SUCCESS-RATE days=<N> completed=<n> success=<n> rate=<x.xxxx>``.
Release reviews use a 30 day window.
"""
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

REPOSITORY = "zlxlabs/ci-infra-canary"
WINDOWS = {"1": 1, "7": 7, "30": 30}


def fetch_conclusions(since, run=subprocess.run):
    proc = run(
        [
            "gh", "api", "--paginate",
            f"repos/{REPOSITORY}/actions/workflows/canary.yml/runs"
            f"?status=completed&created=%3E%3D{since}&per_page=100",
            "--jq", ".workflow_runs[].conclusion",
        ],
        check=True, capture_output=True, text=True,
    )
    return proc.stdout.split()


def summarize(conclusions):
    counts = Counter(conclusions)
    completed = sum(counts.values())
    if completed == 0:
        raise SystemExit("CANARY-SUCCESS-RATE-INVALID reason=no_completed_runs")
    return completed, counts["success"], counts["success"] / completed


def main(argv):
    if len(argv) != 2 or argv[1] not in WINDOWS:
        print(f"usage: {argv[0]} <1|7|30>", file=sys.stderr)
        return 2
    days = WINDOWS[argv[1]]
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    completed, success, rate = summarize(fetch_conclusions(since))
    print(f"CANARY-SUCCESS-RATE days={days} completed={completed} success={success} rate={rate:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
