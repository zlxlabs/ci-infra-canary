# tested-evidence 判定脚本日志切片

字节级真实切片，非合成样本。

- `quality-ok.log`：正样本。来自 zlxlabs/ci-infra-canary PR #66 的 `gate / quality`
  job 128658884417 日志（run 42457278905 attempt 1，经
  `gh api repos/zlxlabs/ci-infra-canary/actions/jobs/128658884417/logs` 取回，
  head `f6e9913bbf4e179b3562392eb76186056ed28370`）。保留原日志第 4304-4311 行
  （Emit 步骤 `##[group]Run python3 - <<'PY' || echo "::warning::..."` 头与其脚本回显，
  含 endgroup 前的 WARN 字面量行）与第 4713-4734 行（env 尾、`##[endgroup]`、
  证据行、下一个 `##[group]Run` 起点及其后数行）；中间 ~400 行脚本回显按卡面约定省略。
- `quality-no-emit.log`：负样本。来自 gate 仓 quality job 128486678343 日志
  （本地留档；经 `gh api repos/zlxlabs/gate/actions/jobs/128486678343/logs`
  可复取）第 1-46 行，该 run 无 Emit 步骤（历史 gate），全文件 0 处
  `GATE-TESTED-EVIDENCE` 提及；首行带 BOM。

派生用例（0 条 / 2 条 / 错 head / mode=entry / 区间内 EMIT-FAILED / 区间外伪造行 /
CRLF / BOM）在 `tests/test_verify_tested_evidence.py` 内由正样本文本变换得出。
