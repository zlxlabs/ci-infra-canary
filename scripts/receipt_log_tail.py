#!/usr/bin/env python3
"""Incrementally summarize runner receipt logs.

Runner hosts append one JSON object per line to ``receipts.jsonl`` while jobs
are running.  This collector runs every few minutes, reads what was appended
since the previous run, and folds it into ``summary.json`` together with the
byte offset it has consumed.  The summary is the only copy kept after the
runner log is rotated, so release checks read their counts from it.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterator

OUTCOMES = ("success", "failure", "cancelled")


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"offset": 0, "counts": {name: 0 for name in OUTCOMES}, "runners": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def read_new_lines(path: Path, offset: int) -> tuple[list[str], int]:
    with path.open("rb") as stream:
        stream.seek(offset)
        chunk = stream.read()
    lines = [line.decode("utf-8") for line in chunk.split(b"\n")]
    return [line for line in lines if line.endswith("}")], offset + len(chunk)


def parse(lines: list[str]) -> Iterator[dict]:
    for line in lines:
        record = json.loads(line)
        if record["outcome"] not in OUTCOMES:
            raise ValueError(f"unknown outcome: {record['outcome']}")
        yield record


def fold(state: dict, records: Iterator[dict]) -> dict:
    for record in records:
        state["counts"][record["outcome"]] += 1
        runner = state["runners"].setdefault(record["runner"], {"jobs": 0, "seconds": 0})
        runner["jobs"] += 1
        runner["seconds"] += record["seconds"]
    return state


def save_state(path: Path, state: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def collect(log: Path, summary: Path) -> dict:
    state = load_state(summary)
    lines, offset = read_new_lines(log, state["offset"])
    state = fold(state, parse(lines))
    state["offset"] = offset
    save_state(summary, state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("summary", type=Path)
    args = parser.parse_args()
    print(json.dumps(collect(args.log, args.summary)["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
