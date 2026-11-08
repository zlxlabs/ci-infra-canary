# canary-evidence-job 进度存档（dlg-20261108-072245-dfd42c）

## 阶段 1：现场核查与 fixture 落盘

- **当前阶段**：implementing
- **本段结论**：worktree 干净、HEAD=f720866 与卡面 Base 一致。正样本取自
  `gh api .../jobs/128658884417/logs`（run 42457278905 attempt 1），Emit 区间：
  头在原日志 4304 行、`##[endgroup]` 4725、证据行 4726、下一个 `##[group]Run` 4727；
  job 名在 API 中确认就是字面量 `gate / quality`（job 元数据 API 直接证实），
  attempts 端点 `runs/{id}/attempts/{attempt}/jobs` 形态正确（该 run 共 8 个 job）。
  fixture 两个均 <10KB：正样本 2212B（恰 1 条证据行）、负样本 2847B（0 处提及）。
- **关键决策与已否决方案**：判定脚本语义照抄参考实现；expected head 从事件元数据取
  （workflow 里经 env `EXPECTED_HEAD_SHA` 传入，不走 `${{ }}` 内联进 run 块）。
  已否决：`gh api --paginate`（该 run 仅 8 个 job，超 30 时 `count=0` 会响亮地红，
  符合 fail-loud，不加防御分支）。
- **下一步唯一动作**：跑单测与脚本冒烟，补 gate.yml job 与 test_gate 断言。

## 阶段 2：实现落盘与本地冒烟

- **当前阶段**：implementing
- **本段结论**：已落盘 `scripts/verify_tested_evidence.py`（纯标准库，reason 枚举：
  emit_region_missing / emit_region_ambiguous / emit_region_unterminated /
  evidence_missing / evidence_duplicate / head_sha_mismatch / mode_mismatch /
  emit_failed_in_region）、`tests/test_verify_tested_evidence.py`（10 个用例，
  全部 subprocess 跑真实脚本）、gate.yml `tested-evidence` job、test_gate.py 合约
  断言、README 章节。脚本直接对两个 fixture 冒烟：正样本 ok、负样本
  emit_region_missing rc=1，符合预期。Verify-Mode=ci-standard-v1，本机不跑
  unittest discover，交远程 CI。
- **关键决策与已否决方案**：job 级 permissions 收窄到 actions+contents（覆盖
  workflow 级的 pull-requests: write，最小权限）。
- **下一步唯一动作**：提交、推分支、开 PR（Refs zlxlabs/gate#394）。

## 阶段 3：PR 验证

- **当前阶段**：verifying
- **本段结论**：（待 CI 终态后回填）
- **关键决策与已否决方案**：无
- **下一步唯一动作**：（待 CI 终态后回填）
