import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "receipt_label_coverage.py"
FP = "0123456789ab"


class ReceiptLabelCoverageTests(unittest.TestCase):
    def run_script(self, *requests):
        with tempfile.TemporaryDirectory() as directory:
            paths = []
            for index, request in enumerate(requests):
                path = Path(directory) / f"{index}.json"
                path.write_text(json.dumps(request), encoding="utf-8")
                paths.append(str(path))
            return subprocess.run([sys.executable, str(SCRIPT), *paths], capture_output=True, text=True)

    def request(self, ci="", review="", schema="gate-hub.release-receipt-request.v2"):
        return {"schema": schema, "ci_label": ci, "review_label": review}

    def test_counts_per_host_and_lane(self):
        proc = self.run_script(
            self.request(ci=f"canary-{FP}-ci-i7-ci"),
            self.request(review=f"canary-{FP}-ci-i7-review"),
            self.request(ci=f"canary-{FP}-ci-03-ci"),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {
            "ci-i7": {"ci": 1, "review": 1},
            "ci-03": {"ci": 1, "review": 0},
        })

    def test_unknown_schema_is_rejected(self):
        proc = self.run_script(self.request(schema="v1"))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("RECEIPT-COVERAGE-INVALID schema", proc.stderr)


if __name__ == "__main__":
    unittest.main()
