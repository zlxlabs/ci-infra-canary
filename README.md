# ci-infra-canary

独立、无模型、低成本的 GitHub Actions / self-hosted runner 主动探针。

这是个人自用仓库，不是平台；它不回调业务仓库、Agent 或 Gate 队列，也不发布派生
evidence、Release asset 或其他消费端 schema。

## 当前目标

`ci-infra-canary` 每 30 分钟由 schedule（也可手动 dispatch）运行确定性的 `make test`。
basic workflow 的 job/step 名固定为 `basic-tests` / `Run deterministic basic tests`，
运行标签为 `[self-hosted, linux, x64, ci]`。

同样每 30 分钟，self-probe 在 `ubuntu-latest` 上验证唯一的 `ci/self-probe` open
non-draft PR（base 必须是 `main`），然后从 `origin/main` 重建一个 marker 提交并以精确
旧 SHA 做 `--force-with-lease` 推送。PAT 推送触发该 PR 的真实 `pull_request:synchronize`，
由现有 Gate caller 执行真实 Gate。探针不等待或解释 Gate，也不操作其他 PR、分支或 Agent。
每轮先比较 gate 仓 `refs/tags/v2` 与 `refs/heads/main`；相同则在 checkout canary 前退出，
取值失败或缺 ref 会记为 `unknown` 并继续完整探针流程。

主仓消费端直接读取 GitHub 官方 Actions runs/jobs、PR 和 checks API；这些官方事实是唯一
的结果来源。缺失、重复、draft 或 head/base 不匹配的 self-probe PR 都会使探针失败。

## 责任边界

| 做 | 不做 |
|---|---|
| 每 30 分钟一次轻量、确定性 basic tests | 调模型、业务仓或外部系统 |
| 标签 `[self-hosted, linux, x64, ci]` | 用户 secrets、数据库、自动 rerun |
| 维护自有 `ci/self-probe` PR 的单个 marker 提交 | 创建 synthetic PR、控制其他 Agent 或 Gate 队列 |
| 从 main 转发 canary 定向标签变量（gate.yml，见下节） | 操作 gate-hub 发布流水线的 receipt 通道 PR（唯一写者是流水线，见下节） |
| 让 GitHub 官方 run/job/check 事实可直接查询 | 生成 evidence 文件、Release asset 或 READY verdict |

失败时不自动修 runner；排查顺序：标签 → runner group 仓库访问策略。回滚仅 disable
workflow，保留历史 run。

## gate-hub 发布流水线 receipt 通道（声明，issue#25 / gate-hub#1724）

gate-hub 发布流水线（`runner/release-pipeline/`）的 receipt 阶段需要一条与
`ci/self-probe` 分开的长期 Gate 通道，避免两个写者共用分支/PR 互相取消：

- 通道是分支 `ci/release-receipt`（base `main`）上的一个长期 open、非 draft PR，
  内含非 Markdown 标记文件 `.ci-release-receipt`（`gate.yml` 的
  `paths-ignore: '**.md'` 只豁免纯 Markdown 差异，标记文件保证 Gate 必触发）。
- 该 PR 的创建与空 marker 推送由 gate-hub 发布流水线独家负责，本仓 workflow 不
  创建、不推送、不合并它。
- self-probe 不创建、不重建、不操作该分支与 PR，与 `ci/self-probe` 互不可见。
  通道由主脑在实现 PR 合并后创建，本文先行声明契约。
- 配套地，main 的 `gate.yml` 把仓库变量 `GATEHUB_CANARY_RUNNER_LABEL_CI` /
  `GATEHUB_CANARY_RUNNER_LABEL_REVIEW` 转发给 gate-v2 输入
  `extra_runner_label_ci` / `extra_runner_label_review`（gate#380）；变量未设时
  为空串，行为与不带标签逐字一致。self-probe 每次从 main 重建 `ci/self-probe`
  自带这两行，不再依赖只活在分支上的配置。

## 本地验证

```bash
make test
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check
```

## 手动入口

合并后的真实入口由主脑按验收流程分别触发和观察；本实现阶段不执行 workflow_dispatch，
不标记 ready，不 merge：

首次接入顺序：合并实现 PR → 确认唯一长期 non-draft `ci/self-probe` PR → dispatch self-probe。
验收只认该 dispatch 触发的 `pull_request:synchronize`，且 `gate/primary` 与 `gate/gate` 均为实际 SUCCESS；
Draft 期间的绿色结果或任一 SKIPPED 均不算真实 Gate 证据。

```bash
gh run list --repo zlxlabs/ci-infra-canary --workflow canary.yml --limit 3
gh run view <run-id> --repo zlxlabs/ci-infra-canary \
  --json databaseId,status,conclusion,url,startedAt,updatedAt,headSha,attempt,jobs
```

`gate.yml` 是普通 PR 的 Gate v2 caller（personal/self/has_ui=false）。self-probe PR
通过 `pull_request:synchronize` 使用同一 caller，Gate 结果直接以 GitHub 官方 checks
呈现。

canary 的 gate run 成功结束后，`notify-gate.yml` 通过 `workflow_run` 通知 `zlxlabs/gate`
重新评估 v2 抬升，发送固定事件 `canary-verified`。它使用 `GATE_DISPATCH_TOKEN` secret；
必须挂在 `workflow_run` 上，因为 gate run 内的 job 执行时该 run 的 `conclusion` 仍是 `null`，
消费方无法据此确认 canary 已跑绿。

## 相关

- 需求与验收：`zlxlabs/gate-hub#247`
