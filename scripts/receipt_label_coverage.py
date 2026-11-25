#!/usr/bin/env python3
"""Report which hosts a batch of release receipt requests covered.

usage: receipt_label_coverage.py <request.json>...

Each argument is one ``.ci-release-receipt`` file.  Prints one JSON object:
``{"<host>": {"ci": <count>, "review": <count>}}``.  The label format is the
one documented in README.md ("receipt 标签按类带后缀").
"""
import json
import re
import sys
from pathlib import Path

SCHEMA = "gate-hub.release-receipt-request.v2"
LABEL = re.compile(r"canary-(?P<fingerprint>[0-9a-f]{12})-(?P<host>[a-z0-9][a-z0-9-]*)-(?P<lane>ci|review)")


def invalid(reason, path):
    raise SystemExit(f"RECEIPT-COVERAGE-INVALID {reason} path={path}")


def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        invalid("not-json", path)
    if not isinstance(data, dict):
        invalid("not-json", path)
    if data.get("schema") != SCHEMA:
        invalid("schema", path)
    for key in ("ci_label", "review_label"):
        if not isinstance(data.get(key), str):
            invalid(key, path)
    return data


def coverage(requests):
    hosts = {}
    for request in requests:
        for key in ("ci_label", "review_label"):
            match = LABEL.fullmatch(request[key])
            if match is None:
                continue
            lanes = hosts.setdefault(match["host"], {"ci": 0, "review": 0})
            lanes[match["lane"]] += 1
    return hosts


def main(argv):
    if len(argv) < 2:
        print(f"usage: {argv[0]} <request.json>...", file=sys.stderr)
        return 2
    print(json.dumps(coverage(load(path) for path in argv[1:]), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
