import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class NotifyGateWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/notify-gate.yml").read_text()

    def test_notifies_only_after_successful_gate_workflow_run(self):
        self.assertIn("name: notify-gate", self.workflow)
        self.assertIn("workflow_run:", self.workflow)
        self.assertIn('workflows: ["gate"]', self.workflow)
        self.assertIn("types: [completed]", self.workflow)
        self.assertRegex(
            self.workflow,
            r"(?ms)^jobs:\n\s+notify-gate:\n\s+if: "
            r"github\.event\.workflow_run\.conclusion == 'success'\s*$",
        )
        self.assertIn("runs-on: ubuntu-latest", self.workflow)
        self.assertIn("timeout-minutes: 2", self.workflow)
        self.assertIn("permissions: {}", self.workflow)
        self.assertNotIn("actions/checkout", self.workflow)

    def test_gate_workflow_has_no_dispatch_path(self):
        # Keep the emitter outside gate.yml: its run conclusion is still null
        # until the gate run itself has completed.
        gate_workflow = (ROOT / ".github/workflows/gate.yml").read_text()
        self.assertNotIn("dispatches", gate_workflow)
        self.assertNotIn("GATE_DISPATCH_TOKEN", gate_workflow)

    def test_sends_fixed_event_without_payload(self):
        self.assertRegex(
            self.workflow,
            r"(?m)^\s+gh api --method POST repos/zlxlabs/gate/dispatches "
            r"-f event_type=canary-verified\s*$",
        )
        self.assertNotIn("client_payload", self.workflow)

    def test_dispatch_failure_is_loud(self):
        self.assertIn("set -euo pipefail", self.workflow)
        self.assertIn('[[ -n "${GH_TOKEN}" ]]', self.workflow)
        self.assertIn("GH_TOKEN: ${{ secrets.GATE_DISPATCH_TOKEN }}", self.workflow)
        self.assertEqual(self.workflow.count("secrets.GATE_DISPATCH_TOKEN"), 1)
        self.assertIn("GATE_DISPATCH_TOKEN", self.workflow)
        for forbidden in ("continue-on-error", "|| true", "retry"):
            self.assertNotIn(forbidden, self.workflow)


if __name__ == "__main__":
    unittest.main()
