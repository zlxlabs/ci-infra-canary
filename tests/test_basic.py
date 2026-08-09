import json
import platform
import sys
import unittest


class BasicCanaryTests(unittest.TestCase):
    def test_python_runtime_is_supported(self):
        self.assertGreaterEqual(sys.version_info[:2], (3, 9))

    def test_json_round_trip_is_deterministic(self):
        payload = {"suite": "basic", "checks": ["python", "json"]}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.assertEqual(json.loads(encoded), payload)
        self.assertEqual(encoded, '{"checks":["python","json"],"suite":"basic"}')

    def test_basic_suite_has_fixed_name(self):
        self.assertEqual("basic_tests", "basic_" + "tests")


if __name__ == "__main__":
    unittest.main()
