# cardB-ci-infra-canary-workflow 进度存档

## 段 1（2026-11-10 前期实测完成）

- **当前阶段**：implementing——前置实测完毕，开始落盘 workflow。
- **本段结论**：ACR 个人版（crpi-0vsre5argteykh9m.cn-guangzhou.personal.cr.aliyuncs.com）按 tag 清理的可行链路已实测三轮：registry v2 `DELETE /v2/<name>/manifests/<tag>` 返回 400 DIGEST_INVALID（按 tag 删不可用），但 `GET /v2/<name>/manifests/<tag>`（Accept 需含 OCI manifest/index 类型）→ 取 `Docker-Content-Digest` header → `DELETE /v2/<name>/manifests/<digest>` → 202 成功；读回 `docker manifest inspect` 返回 `no such manifest`。token dance 端点 `https://dockerauth-cn-guangzhou.aliyuncs.com/auth`（service `registry.aliyuncs.com:cn-guangzhou:26842`），scope `repository:<name>:*`，凭据可经 curl `--config -`（stdin）传递，实测密码/用户名不含引号、反斜杠、空白（字符集校验须进 workflow，不满足即 fail-loud）。ACR 凭据是「邮箱+固定密码」形态而非 AK，阿里云 OpenAPI（aliyun CLI / DeleteTag）路线不可用——本机无 aliyun CLI 也无 AK。
- **关键决策与已否决方案**：否决 aliyun OpenAPI 删 tag（无 AK 凭据，自造凭据被卡面禁止）；否决 `docker manifest inspect -v` 提取 digest（输出结构对单 manifest/index 形状不同，curl HEAD + Docker-Content-Digest header 更稳定）；清理读回确认用 `docker manifest inspect` 必须命中 `no such manifest`（主脑预取已实测该文案）。gate-v2 在同型 slot 上大量使用 python3/gh/curl，故 slot 内 python3 生成回执 JSON 是安全的。`canary_label` 精确格式锁定为 `canary-[0-9a-f]{12}-[a-z0-9][a-z0-9-]*-ci`（canary_window.py:60-67），`expected_runner_prefix` 锁定为 `gatehub-[0-9a-f]{12}-slot-`。
- **下一步唯一动作**：写 `.github/workflows/runner-artifact-canary.yml` 全文。
