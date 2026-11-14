# ci-infra-canary 仓级声明

risk-tier: personal
verify-remote: gate.yml
verify-remote-main: main-verify.yml

本仓验证命令是 `make unit`（unittest discover，跑同一套 tests/）。PR 侧 gate quality
与 main push 侧 main-verify workflow 实际执行 `uv run --frozen pytest -q`
（gate-v2 quality legacy 自动检测对本仓的选择：无 `test:` make target +
pyproject.toml + uv.lock）。risk-tier 取值依据 gate-hub AGENTS.md「附属仓库」表。
