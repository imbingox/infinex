# 自动发版与 GHCR 发布：技术设计

## 1. Architecture

发布流程拆为三个权限和职责边界清晰的 workflow：

```text
普通 PR / main push
        |
        v
       CI  ------------------------------> 只做质量检查

手动 Prepare Release
        |
        +--> semantic-release 生成 release commit
        +--> push release/vX.Y.Z
        +--> 创建 release PR
        +--> 显式 workflow_dispatch CI（release branch）

release PR 合并到 main
        |
        v
main CI 成功 --workflow_run--> Publish Release
                                  |
                                  +--> release message/version/tag guard
                                  +--> build + push GHCR
                                  +--> create GitHub Release + tag
```

CI 不拥有写权限。Prepare Release 只负责生成可审查的版本变更。Publish Release 只接受 `main` 上成功的 CI 结果，并在创建 tag 前先完成镜像推送。

## 2. Workflow Contracts

### 2.1 CI

- Trigger：`pull_request`、`push` 到 `main`、`workflow_dispatch`。
- `workflow_dispatch` 专门供 Prepare Release 对 release branch 显式触发检查；Publish Release 的 `workflow_run.branches: [main]` 保证该检查不会触发发布。
- Permission：`contents: read`。
- 保留 PostgreSQL service、backend checks、Bun frozen install 和 Web checks。
- `actions/checkout`、`setup-uv`、`setup-bun` 固定到完整 SHA；Bun 固定到与当前 lockfile 工具链一致的 `1.3.14`。
- Checkout 使用 `persist-credentials: false`。

### 2.2 Prepare Release

- Trigger：仅 `workflow_dispatch`，输入 `release_type=auto|patch|minor|major`。
- Permission：`contents: write`、`pull-requests: write`、`actions: write`。
- 固定 checkout `main`、完整历史和 tags。
- 使用 `python-semantic-release version --no-push --no-tag --no-vcs-release` 生成本地 release commit；运行时通过 `env -u GITHUB_OUTPUT` 避免 semantic-release 在禁用 push/tag 后错误校验 action outputs。
- `auto` 无可发布 commit 时输出 `released=false` 并结束。
- 版本来自更新后的 `pyproject.toml`，branch 固定为 `release/vX.Y.Z`。
- 使用短生命周期的 token remote URL 推送 branch，checkout 不持久化 credential。
- 已有同 head branch PR 时复用；不存在时创建。
- 最后执行 `gh workflow run ci.yml --ref release/vX.Y.Z`，确保 release commit 自动获得 CI，即使 GitHub 抑制由 `GITHUB_TOKEN` 引发的 PR/synchronize 事件。
- Concurrency 固定为单一 prepare group，避免两个版本准备任务竞态。

### 2.3 Publish Release

- Trigger：`workflow_run` 监听 `CI` 在 `main` 上完成，以及 `workflow_dispatch` 手动重试。
- Permission：`contents: write`、`packages: write`。
- 自动触发时只接受 `workflow_run.conclusion == success`；手动触发始终 checkout 当前 `main`，避免从任意选中 branch 发布。
- 从 `pyproject.toml` 读取版本，tag 为 `vX.Y.Z`。
- 检查 `HEAD`；若是 merge commit，再检查 `HEAD^2`。至少一个 commit message 必须匹配 `chore(release): vX.Y.Z`。
- 远端 tag 已存在时输出 `should_publish=false`，实现幂等重跑。
- 使用 Buildx、GHCR login 和 Docker metadata 生成：
  - `ghcr.io/imbingox/infinex:vX.Y.Z`
  - `ghcr.io/imbingox/infinex:X.Y.Z`
  - `ghcr.io/imbingox/infinex:latest`
- 首版只构建 GitHub hosted runner 的 `linux/amd64` 镜像；多架构发布留作后续需求。
- 镜像 push 成功后才运行 `gh release create`。这样 GHCR 失败不会留下不可用的正式 tag。
- 不启用依赖或 Docker layer cache，降低发布产物受共享 cache 影响的风险。

## 3. Versioning

在 `pyproject.toml` 新增 `tool.semantic_release`：

- Conventional Commits：`feat` -> minor，`fix|perf` -> patch。
- `major_on_zero=false`、`allow_zero_version=true`，保持 `0.x` 阶段语义。
- Python 版本唯一来源为 `pyproject.toml:project.version`。
- `CHANGELOG.md` 由 semantic-release 维护。
- `scripts/stamp_web_version.py "$NEW_VERSION"` 更新 `web/package.json`。
- `web/bun.lock` 不保存 workspace package version，因此不纳入版本 stamping 或 semantic-release assets。
- release commit message 固定为 `chore(release): v{version}`，与 Publish Release guard 共用同一契约。

版本脚本保持小而可测试：读取 JSON、更新顶层 `version`、以两空格缩进和结尾换行写回。单元测试在临时目录验证更新结果和非版本字段不变。

## 4. Container Design

### 4.1 Dockerfile

采用三阶段构建：

1. `web-builder`
   - 使用固定 Bun 版本镜像。
   - 先复制 `web/package.json` 与 `web/bun.lock`，执行 `bun install --frozen-lockfile`。
   - 再复制 Web 源码并执行 `bun run build`。
2. `python-builder`
   - 使用 Python 3.13 + 固定 uv 版本镜像。
   - 复制 `pyproject.toml`、`uv.lock`、README、`src/`，执行 `uv sync --frozen --no-dev`。
   - 保持 editable source layout，因为当前 migration discovery 通过 `src/infinex/control_plane/db.py` 向上定位仓库根目录。
3. `runtime`
   - 使用与 builder 兼容的 Python 3.13 slim base。
   - 复制 `.venv`、`src/`、`alembic.ini`、`migrations/` 和 `web/dist`。
   - 创建非 root 应用用户和 `/app/data` 可写目录。
   - 设置 `PATH=/app/.venv/bin:$PATH`、`PYTHONUNBUFFERED=1`。
   - `EXPOSE 8002`，默认 `CMD ["infinex", "serve"]`。

新增 `.dockerignore` 排除 Git/Trellis 元数据、虚拟环境、cache、测试产物、本地数据和 `web/node_modules`/`web/dist`，缩小 build context；Dockerfile 所需 manifest、源码、migration 和 README 不得被排除。

### 4.2 Compose

Compose 按实际机器边界拆为两个部署文件：

- 不内置 PostgreSQL 或其他数据库 service；部署方只通过 `DATABASE_URL` 连接外部数据库。
- `docker-compose.yml`：同机运行 `infinex` 与 `backtest-worker`。Control Plane 默认 build 当前 Dockerfile，也声明可覆盖的 GHCR image；`DATABASE_URL` 未设置或为空时使用 `/app/data/infinex.db` SQLite，设置后直接使用外部 URL。
- `infinex` 使用 8002 端口和 `/api/health` healthcheck；`backtest-worker` 只通过同一 Compose 网络的 `http://infinex:8002` 连接，并等待 Control Plane 健康。
- `docker-compose.live-worker.yml`：只运行 `live-agent`，不声明本地 Control Plane 或 `depends_on`；必须显式传入可路由的 `CONTROL_PLANE_URL` 与稳定唯一的 `LIVE_WORKER_ID`。
- 三个角色分别 bind mount `${INFINEX_DATA_ROOT}/control-plane`、`${INFINEX_DATA_ROOT}/backtest-worker` 和 `${INFINEX_DATA_ROOT}/live-worker`。Compose 不自动创建这些目录，部署前由宿主机创建并授予 runtime UID/GID `10001` 写权限。
- enrollment token 通过 Compose variable substitution 提供带警告性质的开发默认值；文档要求生产环境显式覆盖。
- 不引入旧仓库 Redis、内置 PostgreSQL 或已经不存在的环境变量。

## 5. Remote Repository Setting

实施前远端事实：

```text
default_workflow_permissions=read
can_approve_pull_request_reviews=false
```

实施时执行：

```bash
gh api --method PUT repos/imbingox/infinex/actions/permissions/workflow \
  -f default_workflow_permissions=read \
  -F can_approve_pull_request_reviews=true
```

当前已通过 GitHub API 变更并验证为：

```text
default_workflow_permissions=read
can_approve_pull_request_reviews=true
```

回滚只需用相同命令将布尔值设为 `false`；workflow 文件无需变更，但 Prepare Release 将无法创建 PR。

同时更新仓库 merge 设置：

- `allow_squash_merge=true`
- `allow_merge_commit=false`
- `allow_rebase_merge=false`
- squash commit title 使用 PR title，确保 Conventional Commit 类型进入 `main` 历史。
- 合并后自动删除 head branch。

为 `main` 新建 active ruleset：

- target：`refs/heads/main`
- 禁止 branch deletion 和 non-fast-forward update。
- 所有变更必须通过 pull request。
- `required_approving_review_count=0`，避免个人仓库因无法自审而锁死；要求所有 review conversations resolved。
- required status check 为 CI 的 `test` job，并要求 branch 与最新 `main` 保持同步后再合并。
- 不配置常规 bypass actor；紧急情况由管理员先修改/停用 ruleset，而不是静默绕过发布契约。

当前 ruleset 已创建，名称为 `Protect main`，ID 为 `18858442`，并通过 GitHub API 回读验证。

本任务自身也在 feature branch 上完成，验证后 push 并创建 Conventional Commit 标题的 PR，通过 CI 后由用户 squash merge 到 `main`。

## 6. Security Boundaries

- Publish Release 的写权限 job 不运行 PR head code，只 checkout `main` 的已通过 CI commit。
- `workflow_run` 的 branch filter 与 release commit/version guard 同时存在，避免普通 main commit 发布。
- 所有 GitHub Actions 固定到完整 commit SHA。
- Checkout credential 默认不落盘；push/login 只在对应步骤显式注入 token。
- Docker runtime 使用非 root 用户，不携带前端依赖树或构建工具。
- Compose 默认 token 只用于本地示例，不能视为生产 secret。

## 7. Compatibility and Rollback

- 日常开发命令、API 和 Web 构建方式不变。
- 新增 `workflow_dispatch` 不改变普通 CI 的自动触发语义。
- 发布流程尚未触发前，回滚只需删除新增 workflow/config/container 文件并恢复 CI。
- 已推送 GHCR 后如需撤回，必须单独删除 package version；删除 Git tag/Release 属于远端破坏性操作，不由自动 workflow 执行。
- 版本发布一旦完成，不通过重写相同 tag 修复；应准备下一个 patch release。
- Ruleset 配置错误导致无法合并时，由管理员将其设为 disabled 或删除；不通过 force push 绕过。
