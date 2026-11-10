# card-2246a-canary-local-leg 进度存档

## 2026-11-10 — 里程碑 1：实现 + 契约测试落地

- **当前阶段**：implementing
- **本段结论**：workflow 已完成三处改动（`LOCAL_REGISTRY` job env 常量打开 push_to_acr.sh 真实双推路径；新增 `Read back local registry digest` 硬闸步骤，用 `docker buildx imagetools inspect --format '{{json .Manifest}}'` 从 registry 侧读回 digest；新增 `Pull probe image from local registry on deploy host` advisory 步骤，rc 用 `if !` 显式捕获、恒 `exit 0`，状态写 `canary-local-pull-status`/`canary-local-pull-digests` 两个 RUNNER_TEMP 文件）。回执追加 `local_ref`/`local_tag`/`local_digest`/`local_pull` 四字段，verdict 增加 `local_ok`（receipt 侧独立 re.fullmatch 校验 digest 形状），失败兜底 reason 为 `local-push-failed`。`make unit` 50 个测试全绿。
- **关键决策与已否决方案**：LOCAL_REGISTRY 走 job env 继承、不在 push 步骤内联重写（内联 `$LOCAL_REGISTRY` 自赋值是纯噪声）；否决了给 local-pull 用 `continue-on-error`（卡面明令禁止，回执拿不到状态）；否决了用 `docker image inspect` 读回（读本机缓存，卡面明令禁止）。新增测试红验证据：base 提交 `9e3143b` 的 workflow 与测试文件中，`Read back local registry digest`/`Pull probe image from local registry`/`local-pull`/`LOCAL_REGISTRY: zlx-vm-` 及三个新测试函数名出现次数均为 0（grep -c 实测），新测试在 base 上必然失败。
- **下一步唯一动作**：提交、推送、开 ready PR（正文 `Refs zlxlabs/gate-hub#2246`），然后核实舰队是否有可派发的 canary label 决定实跑或移交主脑。

## 2026-11-10 — 里程碑 2：PR 已开（ready），实跑移交主脑

- **当前阶段**：implementing（收尾）
- **本段结论**：PR #76 已开且非 draft（head d6043b6 起）。推送时踩到两处坑并已修：① pre-push public-scan 拦裸用户名 token（ identities 表 username 规则是 token 边界匹配，域名前缀形式不命中），进度文件里一处裸引用已改写；② local-pull 步骤初稿用 `if ! remote_out=$(ssh ...)` 捕 rc，bash 里 `!` 取反后 else 分支内 `$?` 恒为 0（bash 实测验证），已改为 plain if/else 捕真实 rc，并加了 `assertNotIn("if ! remote_out=")` 测试锁死。修改后 `make unit` 50 全绿。
- **关键决策与已否决方案**：实跑移交主脑——组织级 runner 盘点（gh api orgs/zlxlabs/actions/runners --paginate）当前 canary-* label 数为 0，canary label 只在滚动窗口内由 gate-hub 侧写入 slot 注册标签；今天上午 09:41Z 的成功 run（42792809954）用的 canary-a91be42ef48d-ci-03-ci 已随窗口关闭消失，现在用 canary label 派发只会永远排队。回执参数参考值已从该 run 的 receipt artifact 取到（candidate 7a9645edf67ccbd2a513b7af2b8123d4039dc934、templates_sha a35caf3becda9d8290d88944ab0ca9f6de11c60b、docker_server_version 29.9.3、runner gatehub-3cbb658164c9-slot-71）。
- **下一步唯一动作**：写 report.md（含 delegate_report_contract skeleton），交主脑在下一个 canary 窗口实跑验收。
