import unittest
from pathlib import Path

class GateCallerContractTests(unittest.TestCase):
    def test_gate_caller_uses_verified_pin_and_secret_mapping(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/gate.yml").read_text()
        self.assertRegex(workflow, r"uses:\s+zlxlabs/gate/\.github/workflows/gate-v2\.yml@7bd2bbd2e92c33d3e0381e38730beaff1f1d69e5\b")
        self.assertRegex(workflow, r"FEISHU_CI_WEBHOOK:\s*\$\{\{\s*secrets\.FEISHU_CI_WEBHOOK\s*\}\}")
