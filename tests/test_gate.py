import unittest
from pathlib import Path

class GateCallerContractTests(unittest.TestCase):
    def test_gate_caller_uses_verified_pin_and_secret_mapping(self):
        workflow = (Path(__file__).parents[1] / ".github/workflows/gate.yml").read_text()
        self.assertRegex(workflow, r"uses:\s+zlxlabs/gate/\.github/workflows/gate-v2\.yml@33fbd932cf8cf89130dfc8f170320764267b4d8a\b")
        self.assertRegex(workflow, r"FEISHU_CI_WEBHOOK:\s*\$\{\{\s*secrets\.FEISHU_CI_WEBHOOK\s*\}\}")
