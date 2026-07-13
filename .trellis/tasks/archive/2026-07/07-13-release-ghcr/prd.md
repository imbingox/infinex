# 自动发版与 GHCR 发布

## Goal

为 Infinex 建立可审查、可重试的正式版本发布流程：日常 PR 与 `main` push 只执行 CI；维护者按需准备 release PR；release PR 合并并通过 `main` CI 后，自动创建 Git tag、GitHub Release，并将可运行的生产镜像推送到 GHCR。

## Background

- 当前仓库只有 `.github/workflows/ci.yml`，没有 release、Git tag、GitHub Release、Docker 或 GHCR 流程。
- Python 与 Web 当前版本均为 `0.1.0`，分别位于 `pyproject.toml` 和 `web/package.json`。
- Web 使用 Bun 与 `web/bun.lock`，生产构建产物是 `web/dist`；FastAPI 已能直接提供该目录。
- 生产入口为 `infinex serve`，同一个 Python 包还提供 worker 子命令，因此同一个镜像应允许通过覆盖 command 运行不同角色。
- Git remote 为 `github.com/imbingox/infinex`，目标镜像名为 `ghcr.io/imbingox/infinex`。
- 历史讨论已确定项目前期只发布正式版本，不发布 beta/canary，也不为普通 PR 或每次 `main` push 推送镜像；同时需要提供 Compose 使用示例。
- 旧仓库的发布规范和 workflow 可作为行为参考，但不得直接复制其中的 npm/package-lock、旧环境变量或旧运行拓扑。

## Requirements

### R1 — CI 与发布隔离

- PR 与 `main` push 继续只执行质量检查。
- CI 不修改版本文件、不创建 tag、不创建 GitHub Release、不推送 GHCR 镜像。
- CI 和 release workflows 的 permissions 遵循最小权限原则。
- 所有产品代码、workflow 和 release commit 均通过 PR 合入 `main`；仓库禁止直接 push、force push 和删除 `main`。
- 仓库只允许 squash merge，PR title 必须使用 Conventional Commit 格式，使 squash commit 成为 semantic-release 的稳定输入。
- `main` ruleset 要求 PR 和成功的 CI；个人仓库不要求强制他人 approval，但要求解决 review conversation。

### R2 — 手动准备正式版本

- 新增仅由 `workflow_dispatch` 触发的 Prepare Release workflow。
- 支持 `auto`、`patch`、`minor`、`major` 四种版本选择；`auto` 使用 Conventional Commits 推导版本。
- workflow 必须固定从 `main` checkout，生成 release commit，但不直接 push `main`、不创建 tag、不创建 GitHub Release。
- release commit 同步更新 `pyproject.toml`、`CHANGELOG.md` 和 `web/package.json`。
- release commit 推送到 `release/vX.Y.Z`，并创建标题为 `chore(release): vX.Y.Z` 的 PR。
- 没有可发布 commit 时不创建 release PR。
- 同一 release branch 已有 PR 时保持幂等，不重复创建。
- 仓库保持 `default_workflow_permissions=read`，开启 `can_approve_pull_request_reviews=true`，允许显式声明 `pull-requests: write` 的 Prepare Release workflow 创建 PR。
- Prepare Release 使用内置 `GITHUB_TOKEN`，不新增 PAT/GitHub App secret；推送 release branch 后显式 dispatch CI，避免 token 创建/更新 PR 时 GitHub 抑制递归 workflow 触发。

### R3 — CI 成功后发布正式版本

- 新增 Publish Release workflow，在 `main` 的 `CI` 成功后运行，并允许 `workflow_dispatch` 手动重试。
- 只有候选 commit message 与当前 `pyproject.toml` 版本匹配 `chore(release): vX.Y.Z` 时才发布。
- tag 已存在时跳过，保证重跑幂等。
- 发布顺序为：构建并推送 GHCR 镜像成功后，再创建 GitHub Release/tag；镜像失败时不得留下已发布 tag。
- Stable release 推送 `vX.Y.Z`、`X.Y.Z`、`latest` 三个 image tags。
- GitHub Release 以对应 release commit/merge commit 为 target，并生成 release notes。

### R4 — 生产镜像

- 新增多阶段 Dockerfile：Bun 阶段构建 `web/dist`，uv/Python 阶段安装 frozen production dependencies，runtime 只携带运行所需 Python 环境、源码和 Web 静态产物。
- runtime 不包含完整 `web/node_modules`、Web 源码或 Bun/Node runtime。
- 默认入口运行 `infinex serve` 并暴露应用端口。
- 镜像支持通过环境变量配置数据库、数据目录和 worker enrollment token，且支持覆盖 command 运行 worker 子命令。
- 提供与当前配置和命令一致的 Compose 示例，不复用旧仓库已失效的 Redis/路径配置。
- Compose 不内置 PostgreSQL 等数据库 service；只接受可选 `DATABASE_URL`，未设置或为空时使用持久化 SQLite。
- `docker-compose.yml` 在同一台机器部署 Control Plane 与 backtest worker；live worker 使用独立 Compose 文件，通过可路由的 `CONTROL_PLANE_URL` 部署到其他机器。
- Compose 数据持久化使用可配置的宿主机目录 bind mount，Control Plane、backtest worker 和 live worker 的数据目录互相独立，便于停机复制和迁移。

### R5 — 版本与供应链约束

- 使用 `python-semantic-release` 管理 Conventional Commits、版本 bump、release commit 和 changelog。
- 新增版本同步脚本，只修改当前实际需要同步的 Web 元数据；不得假设存在 npm `package-lock.json`。
- GitHub Actions 的 `uses:` 必须固定到完整 commit SHA。
- Checkout 默认 `persist-credentials: false`；只有确实需要写入远端的步骤通过显式 token URL 完成。
- 发布 job 不启用依赖缓存。
- 更新 `.trellis/spec/ops/`，将落地后的 CI、release、Docker/GHCR 契约记录为当前项目规范。

## Acceptance Criteria

- [x] AC1：`.github/workflows/ci.yml` 在 PR / push 时只运行现有 backend 与 Web 检查，使用最小权限且 action 固定到 SHA。
- [x] AC1a：`main` ruleset 禁止直接/强制 push 和 branch deletion，要求 PR 与 CI；仓库仅允许 squash merge。
- [x] AC2：Prepare Release 可按 `auto|patch|minor|major` 生成同步 Python/Web 版本与 changelog 的 release PR，不直接修改 `main` 或创建 tag。
- [x] AC3：非 release commit 的成功 CI 不发布；匹配版本的 release commit 在 CI 成功后发布 GitHub Release 和 GHCR stable tags。
- [x] AC4：Publish Release 在 tag 已存在时安全跳过；GHCR build/push 失败时 tag/GitHub Release 尚未创建。
- [x] AC5：Docker image 可使用 `infinex serve` 启动并提供已构建 Web；runtime 不包含前端构建工具或源码。
- [x] AC6：两套 Compose 配置均能够通过 `docker compose config`，不内置数据库 service；Control Plane 与 backtest worker 同机运行，live worker 可通过外部 URL 独立部署；空 `DATABASE_URL` 使用 bind mount 目录中的 SQLite，非空值传给 Control Plane。
- [x] AC7：版本同步脚本有自动化测试，能够更新 `web/package.json` 且保持有效 JSON。
- [x] AC8：所有 workflows 通过 `uvx zizmor .github/workflows`；相关 backend/Web 测试和构建通过。
- [x] AC9：ops spec 更新为落地后的事实，并记录仓库设置中允许 Actions 创建 PR这一外部前置条件。

## Out of Scope

- beta、alpha、rc、nightly、canary 或 `main` 浮动镜像。
- 为每个 PR 构建或推送 GHCR 镜像。
- 自动部署到服务器、Kubernetes 或云平台。
- 绕过 `main` branch protection/ruleset 直接推送 release commit。
- 除 Control Plane/backtest 同机与 live worker 独立部署示例之外的应用运行拓扑重构或生产级数据库运维方案。
