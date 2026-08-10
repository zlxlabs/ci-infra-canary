import json
import sys
import unittest
from pathlib import Path


class BasicCanaryTests(unittest.TestCase):
    def test_python_runtime_is_supported(self):
        self.assertGreaterEqual(sys.version_info[:2], (3, 9))

    def test_json_round_trip_is_deterministic(self):
        payload = {"suite": "basic", "checks": ["python", "json"]}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.assertEqual(json.loads(encoded), payload)
        self.assertEqual(encoded, '{"checks":["python","json"],"suite":"basic"}')

    def test_canary_required_files_exist(self):
        root = Path(__file__).parents[1]
        for relative_path in (
            ".github/workflows/canary.yml",
            ".github/workflows/gate.yml",
            ".github/workflows/self-probe.yml",
            "Makefile",
        ):
            self.assertTrue((root / relative_path).is_file(), relative_path)

    def test_evidence_publisher_paths_are_removed(self):
        root = Path(__file__).parents[1]
        for relative_path in (
            ".github/workflows/publish-evidence.yml",
            "scripts/build_evidence.py",
            "tests/test_build_evidence.py",
        ):
            self.assertFalse((root / relative_path).exists(), relative_path)


if __name__ == "__main__":
    unittest.main()
