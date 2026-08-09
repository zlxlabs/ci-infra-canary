# ci-infra-canary

独立、无模型、低成本的 **GitHub Actions / self-hosted runner 主动 canary**。

个人自用；不是平台。消费端（例如 AiUsageMonitor）只读 GitHub API 或公开 release
asset，本仓不回调业务仓库、Agent 或 Gate 队列。

## 当前目标

每 30 分钟一次的 schedule 和 `workflow_dispatch` 都会真实执行 `make test`。运行结束
后发布 schema v1 readiness evidence：

- 每 run 的 immutable artifact：`ci-readiness-evidence-v1-${run_id}-${run_attempt}`，入口文件为 `ci-readiness-evidence-v1.json`。
- 固定 release/tag `ci-readiness-evidence-v1` 的最新公开 asset：
  `https://github.com/zlxlabs/ci-infra-canary/releases/download/ci-readiness-evidence-v1/ci-readiness-evidence-v1.json`。
- basic 测试失败时，先发布 failure evidence，再让 workflow 以非零状态结束。
- `gate_review` 在尚无可用 no-PR Gate 入口前固定为 `execution_proven=false`、`outcome=unavailable`、`review_executed=false`、`verdict=unavailable`；不把普通 workflow 成功冒充 Gate READY。

## Evidence v1

顶层字段为 `schema_version=1`、`observed_at` 和 `lanes.basic_tests` /
`lanes.gate_review`。每个 lane 都包含：

`execution_proven`、`outcome`、`started_at`、`completed_at`、`duration_seconds`、
`run_url`、`head_sha`、`run_attempt`、`trigger`、`cause_domain`、`cause_code`、
`detail`。

`basic_tests` 的 `outcome` 为 `success` 或 `failure`，`duration_seconds` 由实际
开始/完成时间计算，必须是有限非负数。`gate_review` 额外包含
`review_executed`、`verdict` 和 `audit_identity`；当前 verdict 只能诚实为
`unavailable`，audit identity 为 `null`。

JSON 使用 UTF-8、稳定排序键和固定分隔符写出，因此 per-run artifact 与 stable
release asset 可以逐字节比较。

## 责任边界

| 做 | 不做 |
|---|---|
| 每 30 分钟一次轻量、确定性 basic tests | 调模型 / 业务仓 / 外部系统 |
| 标签 `[self-hosted, linux, x64, ci]` | 用户 secrets、数据库、自动 rerun |
| 发布 per-run artifact 与最新公开 release asset | 创建 synthetic PR、控制 Agent 或 Gate |
| 以 JSON evidence 作为只读消费契约 | 伪造 Gate primary 或 READY verdict |

失败时不自动修 runner；排查顺序：标签 → runner group 仓库访问策略。回滚仅 disable
workflow，保留历史 run。

## 本地验证

```bash
make test
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check
```

生成一个本地 schema v1 fixture（不会创建 GitHub release）：

```bash
python3 scripts/build_evidence.py \
  --output /tmp/ci-readiness-evidence-v1.json \
  --observed-at 2026-08-09T00:00:30Z \
  --basic-started-at 2026-08-09T00:00:00Z \
  --basic-completed-at 2026-08-09T00:00:30Z \
  --basic-outcome success \
  --run-url https://github.com/zlxlabs/ci-infra-canary/actions/runs/0 \
  --head-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --run-attempt 1 \
  --trigger schedule \
  --basic-detail 'local fixture'
```

## 手动入口

合并后的真实入口由主脑按验收流程分别触发和观察；本实现阶段不执行
`workflow_dispatch`，不创建 release，也不标记 ready：

```bash
gh workflow run canary.yml --repo zlxlabs/ci-infra-canary
gh run list --repo zlxlabs/ci-infra-canary --workflow canary.yml --limit 3
gh run view <run-id> --repo zlxlabs/ci-infra-canary --json databaseId,status,conclusion,url,startedAt,updatedAt,headSha,attempt,jobs
```

## 相关

- 需求与验收：`zlxlabs/gate-hub#247`
- 被动 registry 哨兵背景：`zlxlabs/AiUsageMonitor#19` / gate-hub `#212`
