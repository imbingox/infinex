# 自动发版与 GHCR 发布：实施计划

## 1. Workflow 与版本基础

- [x] 查询并记录 `actions/checkout`、`setup-uv`、`setup-bun`、Docker actions 当前稳定 tag 对应的完整 commit SHA。
- [x] 更新 `.github/workflows/ci.yml`：最小权限、`main` push filter、`workflow_dispatch`、固定 action SHA、固定 Bun 版本、禁用 checkout credential persistence。
- [x] 在 `pyproject.toml` 新增 `tool.semantic_release` 配置。
- [x] 新增 `CHANGELOG.md`。
- [x] 新增 `scripts/stamp_web_version.py` 和对应单元测试，只同步 `web/package.json`。
- [x] 新增 `.github/workflows/prepare-release.yml`，实现版本选择、release commit、branch/PR 幂等和显式 dispatch CI。
- [x] 新增 `.github/workflows/publish-release.yml`，实现 main CI guard、版本/tag 幂等检查、GHCR publish 后创建 GitHub Release。

## 2. Container 与使用文档

- [x] 新增 `.dockerignore`。
- [x] 新增三阶段 `Dockerfile`，包含 Bun Web build、uv frozen production install、非 root runtime 和 migration/Web 产物。
- [x] 调整 `docker-compose.yml`：同机运行默认 SQLite/可选外部 `DATABASE_URL` 的 Control Plane 与 backtest worker；使用独立宿主机目录 bind mount，不内置数据库 service。
- [x] 新增 `docker-compose.live-worker.yml`：live worker 通过显式外部 `CONTROL_PLANE_URL` 独立部署，使用独立宿主机目录保存凭据和工作数据。
- [x] 新增独立的 Control Plane/live worker Compose 环境变量示例并更新 `README.md`，说明 image/data root、worker ID、两套 Compose、目录权限、迁移方式和 enrollment token；不向应用 `.env.example` 混入 Pydantic 未声明字段。

## 3. Repository Setting 与规范

- [x] 将远端 `can_approve_pull_request_reviews` 设置为 `true`，保持 `default_workflow_permissions=read`，随后读取 API 验证。
- [x] 更新仓库 merge 设置为仅允许 squash merge，并让 squash commit title 使用 PR title。
- [x] 创建 `main` active ruleset：要求 PR、CI `test` check 和 conversation resolution，禁止 deletion/non-fast-forward，不要求个人仓库 approval。
- [x] 更新 `.trellis/spec/ops/index.md`，将 release/Docker/GHCR 纳入已落地范围。
- [x] 重写 `.trellis/spec/ops/github-actions-guidelines.md`，记录当前 CI、Prepare Release、Publish Release、semantic-release、Docker/GHCR 契约、错误矩阵和验证方式。

## 4. Validation

- [x] `git diff --check`
- [x] `uv run pytest tests/test_stamp_web_version.py`
- [x] `uv run ruff check .`
- [x] `uv run ruff format --check .`
- [x] `uv run pytest -q`
- [x] `cd web && bun install --frozen-lockfile`
- [x] `cd web && bun run typecheck`
- [x] `cd web && bun test`
- [x] `cd web && bun run build`
- [x] 在临时 `main` fixture 中真实运行 `python-semantic-release==10.6.1`，验证首发与后续 minor release 的 Python/Web 版本和 CHANGELOG。
- [x] `uvx zizmor .github/workflows`
- [x] GitHub PR CI 执行 `docker build --tag infinex:ci .` 并成功。
- [x] 使用独立 Docker Compose v5.3.1 CLI 运行两套 Compose 的 `docker compose config`。
- [x] GitHub PR CI 启动镜像并请求 `/api/health` 与 `/`，确认 migration 和 Web 静态产物可用。
- [x] 当前环境无 Docker daemon；已将 image build + runtime smoke test 加入必需的 PR `test` job，等待 GitHub CI 验证，不将静态检查描述为运行验证。

## 5. Review Gates and Rollback Points

- [x] 检查 CI 的 `workflow_dispatch` 不会绕过检查内容，Publish Release 的 `workflow_run.branches` 仍只允许 `main`。
- [x] 检查 Publish Release 在 GHCR push 前不创建 tag/Release。
- [x] 检查所有 `uses:` 均为 40 位 SHA，且 checkout 均显式设置 `persist-credentials: false`。
- [x] 检查 release commit message、semantic-release tag format 和 publish guard 完全一致。
- [x] 检查 Docker runtime 包含 `migrations/` 与 `alembic.ini`，但不包含 `web/node_modules`、Web 源码或 Bun runtime。
- [x] 检查 Compose 不包含旧 Redis 配置和失效环境变量，live worker 不依赖本机 Control Plane service，所有持久数据均使用独立 bind mount 目录。
- [ ] 如远端设置变更需要回滚，将 `can_approve_pull_request_reviews` 恢复为 `false`；代码回滚与远端设置回滚分别执行。
- [x] 验证仓库只允许 squash merge，读取 `main` ruleset 并核对 enforcement、target 和 rules。

## 6. Delivery

- [x] 在 feature branch 上提交本任务改动，commit/PR title 使用 Conventional Commit 格式。
- [x] Push feature branch 并创建 PR，不直接更新 `main`。
- [x] 确认 PR CI 已触发并通过。
- [x] 用户已 review 并 squash merge PR #1。
- [x] 合并后 `main` CI 成功；普通 feature merge 的 Publish guard 正确跳过。
- [x] Prepare Release 成功创建 `chore(release): v0.1.0` PR #2，release branch CI 成功，用户已 squash merge。
- [ ] Publish Release 因既有 GHCR package 未授权当前 repository 写入而失败；修复 package Actions access 后重试。

## 7. Current External Blocker

- `Publish Release` run `29229770744` 在 image push 阶段失败：`permission_denied: write_package`。
- Build 已成功，Git tag 与 GitHub Release 尚未创建，符合“先 image、后 tag”的安全顺序。
- 公开 Registry API 证明 `ghcr.io/imbingox/infinex` 是既有 package，已有 `0.1.0`、`v0.1.0`、`0.1.1`、`v0.1.1`、`latest` tags。
- 当前 repository ID 为 `1297157925`，需要在 package settings 的 Manage Actions access 中授予 `imbingox/infinex` write access。
- feature/release remote branches 均已由 GitHub 在 squash merge 后删除；本地只保留与 `origin/main` 同步的 `main`。
