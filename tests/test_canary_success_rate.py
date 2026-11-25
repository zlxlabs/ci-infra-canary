import importlib.util
import subprocess
import unittest
from pathlib import Path

PATH = Path(__file__).parents[1] / "scripts" / "canary_success_rate.py"
SPEC = importlib.util.spec_from_file_location("canary_success_rate", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CanarySuccessRateTests(unittest.TestCase):
    def test_counts_every_completed_conclusion(self):
        self.assertEqual(
            MODULE.summarize(["success", "failure", "success", "cancelled"]), (4, 2, 0.5)
        )

    def test_no_runs_is_an_error(self):
        with self.assertRaisesRegex(SystemExit, "no_completed_runs"):
            MODULE.summarize([])

    def test_reads_all_pages_since_the_window_start(self):
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, stdout="success\nfailure\n", stderr="")

        self.assertEqual(
            MODULE.fetch_conclusions("2026-11-01T00:00:00Z", run=run), ["success", "failure"]
        )
        argv, kwargs = calls[0]
        self.assertIn("--paginate", argv)
        self.assertIn("created=%3E%3D2026-11-01T00:00:00Z", argv[3])
        self.assertTrue(kwargs["check"])

    def test_gh_failure_propagates(self):
        def run(argv, **kwargs):
            raise subprocess.CalledProcessError(1, argv)

        with self.assertRaises(subprocess.CalledProcessError):
            MODULE.fetch_conclusions("2026-11-01T00:00:00Z", run=run)

    def test_unsupported_window_is_a_usage_error(self):
        self.assertEqual(MODULE.main(["canary_success_rate.py", "31"]), 2)


if __name__ == "__main__":
    unittest.main()
