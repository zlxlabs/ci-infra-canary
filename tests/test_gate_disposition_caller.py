"""caller workflow 契约断言（面向 zlxlabs/gate reusable workflow 输入契约）：

- 调用钉在 @v2（v2 标签只在金丝雀验证绿后才前移，钉它即钉金丝雀验证过的契约）；
- 8 个 workflow_dispatch 输入名与 gate 模板一致且原样转发；
- 公开仓显式映射 SILO_ACCESS_KEY/SILO_SECRET_KEY，不出现 secrets: inherit；
- permissions 与模板一致（顶层与 job 级各一份）。
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).parents[1]
CALLER_PATH = REPO / ".github/workflows/gate-disposition.yml"

INPUTS = [
    "pr_number",
    "primary_run_id",
    "primary_run_attempt",
    "finding_id",
    "reason",
    "disposition",
    "counterevidence_json",
    "tracking_issue",
]


class GateDispositionCallerContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CALLER_PATH.read_text(encoding="utf-8") if CALLER_PATH.exists() else ""

    def test_caller_pins_gate_v2_disposition_at_v2(self):
        self.assertRegex(
            self.text,
            r"(?m)^\s*uses:\s*zlxlabs/gate/\.github/workflows/"
            r"gate-v2-disposition\.yml@v2\s*$",
        )

    def test_declares_exactly_the_template_input_names(self):
        declared = re.findall(r"(?m)^      ([a-z_]+):\s*\{", self.text)
        self.assertEqual(declared, INPUTS)

    def test_forwards_all_inputs_verbatim(self):
        for name in INPUTS:
            pattern = r"(?m)^      " + name + r":\s*" + re.escape("${{ inputs." + name + " }}") + r"\s*$"
            self.assertRegex(self.text, pattern, name)

    def test_no_secrets_inherit(self):
        self.assertNotIn("secrets: inherit", self.text)

    def test_maps_silo_secrets_explicitly(self):
        for secret in ("SILO_ACCESS_KEY", "SILO_SECRET_KEY"):
            pattern = r"(?m)^      " + secret + r":\s*" + re.escape("${{ secrets." + secret + " }}") + r"\s*$"
            self.assertRegex(self.text, pattern, secret)

    def test_permissions_match_template_at_both_levels(self):
        self.assertRegex(
            self.text,
            r"(?m)^permissions:\n  actions: write\n  contents: read\n  pull-requests: read$",
        )
        self.assertRegex(
            self.text,
            r"(?m)^    permissions:\n      actions: write\n      contents: read\n      pull-requests: read$",
        )


if __name__ == "__main__":
    unittest.main()
