# card-2246a-canary-local-leg 进度存档

## 2026-11-10 — 里程碑 1：实现 + 契约测试落地

- **当前阶段**：implementing
- **本段结论**：workflow 已完成三处改动（`LOCAL_REGISTRY` job env 常量打开 push_to_acr.sh 真实双推路径；新增 `Read back local registry digest` 硬闸步骤，用 `docker buildx imagetools inspect --format '{{json .Manifest}}'` 从 registry 侧读回 digest；新增 `Pull probe image from local registry on deploy host` advisory 步骤，rc 用 `if !` 显式捕获、恒 `exit 0`，状态写 `canary-local-pull-status`/`canary-local-pull-digests` 两个 RUNNER_TEMP 文件）。回执追加 `local_ref`/`local_tag`/`local_digest`/`local_pull` 四字段，verdict 增加 `local_ok`（receipt 侧独立 re.fullmatch 校验 digest 形状），失败兜底 reason 为 `local-push-failed`。`make unit` 50 个测试全绿。
- **关键决策与已否决方案**：LOCAL_REGISTRY 走 job env 继承、不在 push 步骤内联重写（内联 `$LOCAL_REGISTRY` 自赋值是纯噪声）；否决了给 local-pull 用 `continue-on-error`（卡面明令禁止，回执拿不到状态）；否决了用 `docker image inspect` 读回（读本机缓存，卡面明令禁止）。新增测试红验证据：base 提交 `9e3143b` 的 workflow 与测试文件中，`Read back local registry digest`/`Pull probe image from local registry`/`local-pull`/`LOCAL_REGISTRY: zlx-vm-` 及三个新测试函数名出现次数均为 0（grep -c 实测），新测试在 base 上必然失败。
- **下一步唯一动作**：提交、推送、开 ready PR（正文 `Refs zlxlabs/gate-hub#2246`），然后核实舰队是否有可派发的 canary label 决定实跑或移交主脑。
