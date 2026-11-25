import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("receipt_log_tail", ROOT / "scripts/receipt_log_tail.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def row(runner, outcome="success", seconds=5):
    return json.dumps({"runner": runner, "outcome": outcome, "seconds": seconds}) + "\n"


class ReceiptLogTailTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = Path(self.directory.name) / "receipts.jsonl"
        self.summary = Path(self.directory.name) / "summary.json"

    def test_second_run_only_counts_appended_rows(self):
        self.log.write_text(row("a") + row("b", "failure"))
        MODULE.collect(self.log, self.summary)
        with self.log.open("a") as stream:
            stream.write(row("a", seconds=7))
        state = MODULE.collect(self.log, self.summary)
        self.assertEqual(state["counts"], {"success": 2, "failure": 1, "cancelled": 0})
        self.assertEqual(state["runners"]["a"], {"jobs": 2, "seconds": 12})

    def test_unknown_outcome_is_an_error(self):
        self.log.write_text(row("a", "skipped"))
        with self.assertRaises(ValueError):
            MODULE.collect(self.log, self.summary)


if __name__ == "__main__":
    unittest.main()
