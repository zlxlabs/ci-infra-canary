import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class MainVerifyWorkflowTests(unittest.TestCase):
    """Static contract for the main-push verify workflow (ci-infra-canary#68).

    agent-config derives Verify-Mode from AGENTS.md verify-remote-main plus a
    workflow that actually fires on main pushes; these assertions keep the
    declared file and its trigger surface from drifting.
    """

    def setUp(self):
        path = ROOT / ".github" / "workflows" / "main-verify.yml"
        self.assertTrue(path.is_file(), ".github/workflows/main-verify.yml missing")
        self.workflow = path.read_text()

    def test_triggers_are_main_push_and_manual_dispatch_only(self):
        on_match = re.search(r"^on:\n(.*?)(?=^\S)", self.workflow, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(on_match, "missing top-level on: block")
        on_block = on_match.group(1)
        events = re.findall(r"^  (\S+):\s*$", on_block, re.MULTILINE)
        self.assertEqual(events, ["push", "workflow_dispatch"])
        branches = re.findall(r"^      - (\S+)$", on_block, re.MULTILINE)
        self.assertEqual(branches, ["main"])
        self.assertIn("    branches:", on_block)
        self.assertNotIn("schedule:", self.workflow)
        self.assertNotIn("pull_request", self.workflow)

    def test_third_party_actions_are_pinned_to_full_sha(self):
        uses = re.findall(r"^\s*(?:-\s+)?uses:\s*(\S+)", self.workflow, re.MULTILINE)
        self.assertTrue(uses, "no uses: entries found")
        for ref in uses:
            action, sep, sha = ref.partition("@")
            self.assertTrue(sep, f"unpinned action ref: {ref}")
            self.assertFalse(action.startswith("./"), f"unexpected local action: {ref}")
            self.assertRegex(sha, r"^[0-9a-f]{40}$", f"ref not a 40-hex SHA: {ref}")

    def test_run_command_matches_gate_quality_detection(self):
        # gate-v2 quality legacy auto-detection order: `make test` (only when a
        # `test:` make target exists) -> package.json -> pyproject.toml (with
        # uv.lock => `uv run --frozen pytest`). This repo has no `test:` target
        # and ships pyproject.toml + uv.lock, so the PR-side gate quality job
        # runs `uv run --frozen pytest -q` — main-verify must run the same.
        makefile = (ROOT / "Makefile").read_text()
        self.assertIsNone(re.search(r"(?m)^test:", makefile))
        self.assertTrue((ROOT / "pyproject.toml").is_file())
        self.assertTrue((ROOT / "uv.lock").is_file())
        self.assertIn("run: uv run --frozen pytest -q", self.workflow)
        self.assertIn("runs-on: [self-hosted, linux, ci]", self.workflow)
        self.assertRegex(self.workflow, r"(?m)^  group: main-verify-\$\{\{ github\.ref \}\}$")
        self.assertIn("cancel-in-progress: true", self.workflow)


class VerifyRemoteDeclarationTests(unittest.TestCase):
    def test_agents_md_declares_workflows_that_exist(self):
        path = ROOT / "AGENTS.md"
        self.assertTrue(path.is_file(), "AGENTS.md missing at repo root")
        agents = path.read_text()
        self.assertRegex(agents, r"(?m)^risk-tier: personal$")
        self.assertRegex(agents, r"(?m)^verify-remote: gate\.yml$")
        self.assertRegex(agents, r"(?m)^verify-remote-main: main-verify\.yml$")
        self.assertTrue((ROOT / ".github" / "workflows" / "gate.yml").is_file())
        self.assertTrue((ROOT / ".github" / "workflows" / "main-verify.yml").is_file())


if __name__ == "__main__":
    unittest.main()
