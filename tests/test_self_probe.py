import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class SelfProbeWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/self-probe.yml").read_text()

    def test_self_probe_is_a_replaceable_ubuntu_schedule(self):
        self.assertRegex(self.workflow, r"cron:\s*[\"']\*/30 \* \* \* \*[\"']")
        self.assertRegex(self.workflow, r"runs-on:\s*ubuntu-latest")
        self.assertRegex(self.workflow, r"concurrency:\s*\n(?:\s+.*\n)*\s+cancel-in-progress:\s*true")

    def test_self_probe_uses_read_only_pr_metadata_and_pat_for_push(self):
        self.assertRegex(self.workflow, r"pull-requests:\s*read")
        self.assertIn("GH_TOKEN: ${{ github.token }}", self.workflow)
        self.assertIn("CI_CANARY_PUSH_TOKEN: ${{ secrets.CI_CANARY_PUSH_TOKEN }}", self.workflow)
        self.assertIn("gh api", self.workflow)
        self.assertRegex(self.workflow, r"state[= ]+open")
        self.assertRegex(self.workflow, r"base[= ]+main")
        self.assertIn("ci/self-probe", self.workflow)
        self.assertRegex(self.workflow, r"draft\s*==\s*false|draft\s*!=\s*true")

    def test_self_probe_rebuilds_main_and_uses_exact_force_with_lease(self):
        self.assertRegex(self.workflow, r"git fetch .*origin.*main")
        self.assertRegex(self.workflow, r"origin/main")
        self.assertIn(".ci-self-probe", self.workflow)
        self.assertRegex(
            self.workflow,
            r"--force-with-lease=refs/heads/ci/self-probe:\$\{old_sha\}",
        )
        self.assertRegex(self.workflow, r"CI_CANARY_PUSH_TOKEN")

    def test_self_probe_rejects_non_unique_or_mismatched_pr(self):
        for phrase in ("length", "head.ref", "base.ref", "draft"):
            self.assertIn(phrase, self.workflow)
        self.assertRegex(self.workflow, r"length\s*==\s*1")

    def test_reduction_removes_publisher_and_release_paths(self):
        self.assertNotIn("workflow_run", self.workflow)
        self.assertNotIn("upload-artifact", self.workflow)
        self.assertNotIn("gh release", self.workflow)


if __name__ == "__main__":
    unittest.main()
