import unittest
from pathlib import Path

class GateCallerContractTests(unittest.TestCase):
    def test_gate_caller_tracks_gate_main_and_maps_secret(self):
        # 这个仓是 gate 侧的金丝雀：它的职责就是拿 zlxlabs/gate 的主干跑在最前面，
        # 给 v2 标签的前移提供「这个提交真的跑绿过」的行为证据。
        # 所以这里断言的是**意图**（跟随 main），不是某个具体 SHA——
        # 钉 SHA 在本仓是错的：每次换钉都会让这条断言过期，
        # 而它过期的表现是门禁红，跟真实缺陷长得一模一样。
        # 钉 @v2 同样是错的，那会构成循环：v2 只前移到金丝雀验过的提交。
        workflow = (Path(__file__).parents[1] / ".github/workflows/gate.yml").read_text()
        self.assertRegex(
            workflow,
            r"(?m)^\s*uses:\s+zlxlabs/gate/\.github/workflows/gate-v2\.yml@main\s*$",
        )
        self.assertRegex(workflow, r"FEISHU_CI_WEBHOOK:\s*\$\{\{\s*secrets\.FEISHU_CI_WEBHOOK\s*\}\}")
