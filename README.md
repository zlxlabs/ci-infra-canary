# ci-infra-canary

独立、无模型、低成本的 **GitHub Actions / self-hosted runner 主动 canary**。

个人自用；不是平台。消费端（例如 AiUsageMonitor）只读 GitHub API，本仓不回调。

## 目的

覆盖被动 SSH 哨兵无法证明的路径：

1. Actions 控制面是否接受并调度作业  
2. `ci` 池 runner 是否能领到并启动作业  
3. 作业是否能在约定 toolchain 上跑通最小 smoke

## 责任边界

| 做 | 不做 |
|---|---|
| 每 30 分钟一次轻量 smoke | 调模型 / 业务仓 / 外部系统 |
| 标签 `[self-hosted, linux, x64, ci]` | 用户 secrets、DB、artifact、自定义 action |
| 输出 runner/OS 与 `python3`/`uv`/`node`/`pnpm`/`docker version` | 自动修复 runner、通知、重试风暴 |
| 以 workflow run 元数据为结果契约 | 向 AiUsageMonitor 或其他系统写回 |

失败时 **不** 自动修 runner；排查顺序：标签 → runner group 仓库访问策略。回滚仅 **disable workflow**，保留历史 run。

## 频率与入口

- Schedule：`*/30 * * * *`（UTC）
- Manual：`workflow_dispatch`

Workflow 文件：`.github/workflows/canary.yml`（手写 ≤60 行，`timeout-minutes: 5`）。

## 结果契约

稳定契约 = GitHub Actions **workflow run** 对象字段（REST/GraphQL 同源），供只读消费：

| 字段 | 含义 |
|---|---|
| `id` | run id |
| `status` | `queued` / `in_progress` / `completed` … |
| `conclusion` | 成功 `success`；失败为非 `success`（如 `failure`/`cancelled`/`timed_out`） |
| `run_started_at` | 开始执行时间 |
| `updated_at` | 最近更新 |
| `html_url` | 人类可读 run URL |
| `run_attempt` | 尝试次数 |
| `head_sha` | 触发时的 commit SHA |

可选观测（日志内，非 API 契约字段）：`runner_name`、排队时长 ≈ `run_started_at - created_at`、执行时长 ≈ `updated_at - run_started_at`（completed 时）。

查询示例：

```bash
gh api repos/zlxlabs/ci-infra-canary/actions/runs \
  --jq '.workflow_runs[0] | {id,status,conclusion,run_started_at,updated_at,html_url,run_attempt,head_sha}'
```

## 手动验证

```bash
gh workflow run canary.yml --repo zlxlabs/ci-infra-canary
gh run list --repo zlxlabs/ci-infra-canary --workflow canary.yml --limit 3
gh run view <run-id> --repo zlxlabs/ci-infra-canary --json databaseId,status,conclusion,url,startedAt,updatedAt,headSha,attempt,jobs
```

## 相关

- 需求与验收：`zlxlabs/gate-hub#247`
- 被动 registry 哨兵背景：`zlxlabs/AiUsageMonitor#19` / gate-hub `#212`
