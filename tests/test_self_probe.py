import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class SelfProbeWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/self-probe.yml").read_text()

    def test_self_probe_is_a_replaceable_ubuntu_schedule(self):
        self.assertRegex(self.workflow, r"cron:\s*[\"']\*/30 \* \* \* \*[\"']")
        self.assertRegex(self.workflow, r"runs-on:\s*ubuntu-latest")
        self.assertIn("  group: ci-self-probe", self.workflow)
        self.assertIn("  cancel-in-progress: true", self.workflow)

    def test_self_probe_uses_read_only_pr_metadata_and_pat_for_push(self):
        self.assertRegex(self.workflow, r"pull-requests:\s*read")
        self.assertIn("GH_TOKEN: ${{ github.token }}", self.workflow)
        self.assertIn("CI_CANARY_PUSH_TOKEN: ${{ secrets.CI_CANARY_PUSH_TOKEN }}", self.workflow)
        self.assertIn("gh api", self.workflow)
        self.assertRegex(self.workflow, r"state[= ]+open")
        self.assertNotIn("-f base=main", self.workflow)
        self.assertIn("ci/self-probe", self.workflow)
        self.assertRegex(self.workflow, r"draft\s*==\s*false|draft\s*!=\s*true")
        self.assertIn('.[0].base.ref == "main"', self.workflow)

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

    def test_gate_content_probe_is_first_and_only_unchanged_skips_work(self):
        probe = self.workflow.index("      - name: Check whether Gate v2 has new content")
        checkout = self.workflow.index("      - name: Checkout canary main")
        self.assertLess(probe, checkout)
        conditions = re.findall(r"^        if: (.+)$", self.workflow, re.MULTILINE)
        self.assertEqual(conditions, ["steps.gate-state.outputs.state != 'unchanged'"] * 3)

    def test_gate_content_probe_states_and_output_file(self):
        lines = self.workflow.splitlines()
        step = next(i for i, line in enumerate(lines) if line == "      - name: Check whether Gate v2 has new content")
        start = next(i for i, line in enumerate(lines[step:], start=step) if line == "        run: |")
        script = []
        for line in lines[start + 1:]:
            if line and not line.startswith("          "):
                break
            script.append(line[10:] if line else "")
        script = "\n".join(script)
        cases = (
            ("111 refs/tags/v2\n111 refs/heads/main\n", 0, "unchanged", "state=unchanged\n"),
            ("111 refs/tags/v2\n222 refs/heads/main\n", 0, "changed", "state=changed\n"),
            ("", 128, "unknown", "state=unknown\n"),
        )
        for response, exit_code, state, output_bytes in cases:
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                bin_dir = Path(tmp) / "bin"
                bin_dir.mkdir()
                fake_git = bin_dir / "git"
                fake_git.write_text("#!/bin/bash\nprintf '%s\\n' \"$@\" > \"$FAKE_ARGS_FILE\"\nprintf '%s' \"$FAKE_REFS\"\nexit \"$FAKE_GIT_EXIT\"\n")
                fake_git.chmod(0o755)
                output = Path(tmp) / "output"
                args_file = Path(tmp) / "args"
                env = os.environ | {
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "GITHUB_OUTPUT": str(output),
                    "FAKE_ARGS_FILE": str(args_file),
                    "FAKE_REFS": response,
                    "FAKE_GIT_EXIT": str(exit_code),
                }
                result = subprocess.run(["bash", "-euo", "pipefail", "-c", script], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"CANARY-NOOP-V1 state={state}", result.stdout)
                self.assertEqual(args_file.read_bytes(), b"ls-remote\nhttps://github.com/zlxlabs/gate.git\nrefs/tags/v2\nrefs/tags/v2^{}\nrefs/heads/main\n")
                self.assertEqual(output.read_bytes(), output_bytes.encode())


if __name__ == "__main__":
    unittest.main()
