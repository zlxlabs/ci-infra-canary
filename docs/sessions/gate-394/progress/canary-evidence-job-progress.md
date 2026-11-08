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

## 阶段 4：首轮 CI 红 → BOM 剥离顺序修复

- **当前阶段**：verifying
- **本段结论**：PR #67 首轮 run 42457278905→42459201865 中 gate / quality 红：
  `test_leading_bom_still_pass` 失败（1 failed, 32 passed），stderr 为
  `reason=emit_region_missing`。根因：脚本把首行 BOM 剥离放在逐行时间戳剥离
  **之后**，首行「BOM+时间戳」时锚定 TS.match 失败、时间戳残留，HEADER 永不匹配；
  参考实现同样顺序（真实日志首行不是 HEADER 所以从未暴露）。修复：BOM 剥离提前到
  逐行解析前（原始字节首行先 lstrip BOM）。修复后 10 个场景（含全部派生用例同变换
  直跑脚本）全绿。教训：Verify-Mode=ci-standard-v1 本机不跑 unittest 的约束下，
  推前仍应用与测试相同的变换直跑脚本冒烟，本轮已补做。
- **关键决策与已否决方案**：保留 BOM 派生用例（卡面派生清单未列，但它暴露了真实
  语义缺陷而非测试恒真）；已否决：删用例迁就参考实现顺序。
- **下一步唯一动作**：推修复 commit，等新一轮 gate run 终态取证。

## 阶段 5：第二轮红（gh 转义序列闸）→ 修复 → E2E 全绿

- **当前阶段**：done
- **本段结论**：run 42459548408：quality 33/33 绿，`tested-evidence` 首次真实运行即红，
  runner gh（≥2.63）拒写含 ANSI 转义字节的日志响应，报错原文要求
  `--allow-escape-sequences`；jobs 列表响应经字节级核验 0 个 ESC 字节，旗标只加在
  日志下载一处。修复后 run 42460302091（attempt 1，head 2ff032f）：run 级
  conclusion=success，`tested-evidence`（job 128669520157）success，日志第 138 行
  打出 `TESTED-EVIDENCE-CHECK ok head_sha=2ff032f5500830119ea1d93665650e3543660fc8
  mode=pytest`，head 与 PR head 逐字相等。附带证据：上一轮 tested-evidence 红 →
  整 run failure → `gate / notify` SKIPPED，下游冻结路径真实存在。
- **关键决策与已否决方案**：已否决：给 jobs 列表调用也加旗标（响应无 ESC 字节，
  若未来含 ESC 会以 gh 自带报错响亮地红，可 grep，符合 fail-loud）。
- **下一步唯一动作**：回填报告、过 report contract check、收尾。
