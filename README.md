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

主仓消费端直接读取 GitHub 官方 Actions runs/jobs、PR 和 checks API；这些官方事实是唯一
的结果来源。缺失、重复、draft 或 head/base 不匹配的 self-probe PR 都会使探针失败。

## 责任边界

| 做 | 不做 |
|---|---|
| 每 30 分钟一次轻量、确定性 basic tests | 调模型、业务仓或外部系统 |
| 标签 `[self-hosted, linux, x64, ci]` | 用户 secrets、数据库、自动 rerun |
| 维护自有 `ci/self-probe` PR 的单个 marker 提交 | 创建 synthetic PR、控制其他 Agent 或 Gate 队列 |
| 让 GitHub 官方 run/job/check 事实可直接查询 | 生成 evidence 文件、Release asset 或 READY verdict |

失败时不自动修 runner；排查顺序：标签 → runner group 仓库访问策略。回滚仅 disable
workflow，保留历史 run。

## 本地验证

```bash
make test
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check
```

## 手动入口

合并后的真实入口由主脑按验收流程分别触发和观察；本实现阶段不执行 workflow_dispatch，
不标记 ready，不 merge：

```bash
gh run list --repo zlxlabs/ci-infra-canary --workflow canary.yml --limit 3
gh run view <run-id> --repo zlxlabs/ci-infra-canary \
  --json databaseId,status,conclusion,url,startedAt,updatedAt,headSha,attempt,jobs
```

`gate.yml` 是普通 PR 的 Gate v2 caller（personal/self/has_ui=false）。self-probe PR
通过 `pull_request:synchronize` 使用同一 caller，Gate 结果直接以 GitHub 官方 checks
呈现。

## 相关

- 需求与验收：`zlxlabs/gate-hub#247`
