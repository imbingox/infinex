# GitHub Actions、正式发布与 GHCR 规范

> 当前 CI、release PR、正式版本、生产镜像和 GitHub 仓库保护契约。

## Scenario: CI 与正式版本发布

### 1. Scope / Trigger

本规范适用于：

- `.github/workflows/ci.yml`
- `.github/workflows/prepare-release.yml`
- `.github/workflows/publish-release.yml`
- `pyproject.toml` 中的 `tool.semantic_release`
- `CHANGELOG.md`
- `scripts/stamp_web_version.py`
- `Dockerfile`、`.dockerignore`、`docker-compose.yml`、`docker-compose.live-worker.yml`、两套 Compose 环境变量示例
- 影响 Git tag、GitHub Release、GHCR image tag、版本文件同步或 `main` ruleset 的改动。

当前策略：普通 PR 与 `main` push 只运行 CI；维护者手动准备 release PR；release PR squash merge 且 `main` CI 成功后自动发布正式版本。项目不发布 beta/canary，也不为普通 PR 或每次 `main` push 推送镜像。

### 2. Signatures

CI triggers：

```yaml
on:
  push:
    branches:
      - main
  pull_request:
  workflow_dispatch:
```

`workflow_dispatch` 是 Prepare Release 显式检查 release branch 的入口，不代表 CI 拥有发布能力。

Prepare Release input：

```yaml
on:
  workflow_dispatch:
    inputs:
      release_type:
        type: choice
        options:
          - auto
          - patch
          - minor
          - major
```

Publish Release triggers：

```yaml
on:
  workflow_run:
    workflows:
      - CI
    types:
      - completed
    branches:
      - main
  workflow_dispatch:
```

生产命令与端口：

```bash
infinex serve
# http://127.0.0.1:8002
```

Compose：

```bash
docker compose up --build
CONTROL_PLANE_URL=https://infinex.example.com \
LIVE_WORKER_ID=live-node-01 \
  docker compose \
    --env-file .env.live-worker \
    -f docker-compose.live-worker.yml \
    up
```

### 3. Contracts

#### CI contract

- Permissions 固定为 `contents: read`。
- `actions/checkout` 设置 `persist-credentials: false`。
- Runner 为 `ubuntu-24.04`。
- Action 固定到完整 commit SHA；uv 固定 `0.11.7`，Python 固定 `3.13`，Bun 固定 `1.3.14`。
- PostgreSQL service 固定 `postgres:17`，数据库为一次性 `infinex_test`，并设置匹配的 `TEST_POSTGRES_URL`。
- Backend 顺序：

  ```bash
  uv sync --extra dev --frozen
  uv run ruff check .
  uv run ruff format --check .
  uv run pytest -q
  ```

- Web 顺序：

  ```bash
  bun install --frozen-lockfile
  bun run typecheck
  bun test
  bun run build
  ```

- CI 最后执行本地 `docker build --tag infinex:ci .`，以 SQLite 默认配置启动临时容器，并断言 `/api/health` 成功且 `/` 包含 Vite root。该镜像只存在于临时 runner，不登录或推送 registry。
- CI 不修改版本、不创建 tag/Release、不登录 GHCR、不推送正式镜像。

#### Prepare Release contract

- 只允许手动触发，且 job 要求 `github.ref == 'refs/heads/main'`；checkout 固定 `ref: main`、`fetch-depth: 0`、`persist-credentials: false`。
- Permissions：`actions: write`、`contents: write`、`pull-requests: write`。
- `auto` 根据 Conventional Commits 推导版本；其余选项强制对应 bump。
- 固定使用：

  ```bash
  env -u GITHUB_OUTPUT \
    uvx --from python-semantic-release==10.6.1 \
    semantic-release version --no-push --no-tag --no-vcs-release
  ```

  强制 bump 时追加 `--patch`、`--minor` 或 `--major`。

- `env -u GITHUB_OUTPUT` 不能删除。prepare 阶段禁用 push/tag，semantic-release 不会生成它在 Actions mode 下要求的全部 outputs；保留该环境变量会在 release commit 已生成后报错。
- release commit 同步 `pyproject.toml`、`CHANGELOG.md`、`web/package.json`；`web/bun.lock` 不保存 workspace version，不参与 stamping。
- release branch 为 `release/vX.Y.Z`，PR title 为 `chore(release): vX.Y.Z`。
- 无可发布 commit 时不创建 branch/PR。
- 同 head branch 已有 PR 时复用，不重复创建。
- 使用内置 `GITHUB_TOKEN` 创建/更新 PR 后，必须执行：

  ```bash
  gh workflow run ci.yml --ref "release/vX.Y.Z"
  ```

  GitHub 会抑制由 `GITHUB_TOKEN` 产生的递归 PR/synchronize workflow；显式 `workflow_dispatch` 保证 release commit 自动获得 `test` check。

#### Publish Release contract

- Permissions：`contents: write`、`packages: write`。
- `workflow_run` 只接受 `main` 上成功的 `CI`；手动重试要求 `github.ref == 'refs/heads/main'` 并固定 checkout 当前 `main`，从其他 ref dispatch 时 job 直接跳过。
- 当前版本只从 `pyproject.toml:project.version` 读取。
- `HEAD` 或 merge commit 的 `HEAD^2` message 必须匹配当前版本的 `chore(release): vX.Y.Z`。
- 本地已获取 tags；`refs/tags/vX.Y.Z` 已存在时跳过，保证重跑幂等。
- 发布顺序固定：GHCR login -> metadata -> build/push -> `gh release create`。镜像失败时不得先留下 Git tag/GitHub Release。
- GHCR image 固定为 `ghcr.io/imbingox/infinex`，首版平台为 `linux/amd64`，正式 tags 为：
  - `vX.Y.Z`
  - `X.Y.Z`
  - `latest`
- Publish job 不启用依赖或 Docker layer cache。

#### Version contract

- Conventional Commit mapping：`feat` -> minor；`fix|perf` -> patch；`build|chore|ci|docs|style|refactor|test` 默认不 bump。
- `major_on_zero=false`、`allow_zero_version=true`，版本前期保持 `0.x` 语义。
- `mask_initial_release=false`，首个正式版本也写入真实 commit 分类，不把完整历史折叠成 `Initial Release`。
- `CHANGELOG.md` 必须保留 `<!-- version list -->` insertion flag；文件有内容但缺少该标记时，python-semantic-release 会保留原文而不插入新版本。
- `scripts/stamp_web_version.py <version>` 只更新 `web/package.json` 顶层 `version`，保留其他字段，输出两空格 JSON 和结尾换行。
- `CHANGELOG.md` 由 python-semantic-release 维护，不手工复制一套版本计算逻辑。

#### Container contract

- Web builder 使用 `oven/bun:1.3.14-slim` 并 pin image digest；安装必须使用 `bun install --frozen-lockfile`。
- Python builder 使用 Python 3.13 slim，并从 pin digest 的 `ghcr.io/astral-sh/uv:0.11.7` 复制 uv；安装必须使用 `uv sync --frozen --no-dev`。
- Runtime 使用非 root `infinex` 用户，只复制 `.venv`、`src/`、`alembic.ini`、`migrations/` 和 `web/dist`。
- Runtime 不复制 `web/node_modules`、Web 源码或 Bun/Node runtime。
- 容器默认使用 `/app/data`、`/app/web/dist`，暴露 `8002`，`CMD` 为 `infinex serve`。
- `docker-compose.yml` 同机启动 Control Plane 与 backtest worker，不内置数据库服务。`DATABASE_URL` 未设置或为空时使用 `/app/data/infinex.db` SQLite；设置后直接连接对应外部数据库。
- `docker-compose.live-worker.yml` 只启动 live worker，不声明本地 Control Plane 或 `depends_on`；必须显式提供可路由的 `CONTROL_PLANE_URL` 与稳定唯一的 `LIVE_WORKER_ID`。
- Control Plane、backtest worker 与 live worker 分别 bind mount `${INFINEX_DATA_ROOT}/control-plane`、`${INFINEX_DATA_ROOT}/backtest-worker`、`${INFINEX_DATA_ROOT}/live-worker`。宿主机必须预创建目录并授予 UID/GID `10001` 写权限；迁移时停机复制对应目录并保留权限。
- Compose 专用变量分别记录在 `.env.control-plane.example` 与 `.env.live-worker.example`；实际部署文件使用被 Git 忽略的无 `.example` 副本，并通过 `docker compose --env-file` 显式加载。应用 `.env.example` 只包含 `Settings` 已声明字段，避免 Pydantic dotenv 的 extra field 校验失败。
- Compose 不得重新引入旧 Redis、内置 PostgreSQL、跨机器 Docker service DNS 或失效环境变量。

#### Repository contract

- `default_workflow_permissions=read`。
- `can_approve_pull_request_reviews=true`，允许显式申请权限的 Prepare Release 创建 PR。
- 仓库只允许 squash merge；squash title 来自 PR title，message 来自 PR body；合并后删除 head branch。
- `Protect main` active ruleset：
  - target `refs/heads/main`
  - 禁止 deletion 与 non-fast-forward
  - required linear history
  - required pull request，allowed merge method 仅 `squash`
  - `required_approving_review_count=0`，但要求 review conversations resolved
  - required status check `test`，strict update policy 开启

PR title 必须使用 Conventional Commit。semantic-release 读取进入 `main` 的 squash commit，而不是把 PR body 当作版本类型来源。

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|-----------|-------------------|
| 普通 PR | 运行 `test`，不发布 |
| 普通 `main` push | 运行 CI；Publish workflow guard 不匹配时跳过 |
| Prepare `auto` 无可发布 commit | 不创建 release branch/PR |
| Prepare 使用 `patch|minor|major` | 强制对应版本 bump 并创建 release PR |
| Actions 创建 PR 开关关闭 | `gh pr create` 失败；恢复 `can_approve_pull_request_reviews=true` |
| bot 创建/更新 release PR | Prepare 显式 dispatch CI，release commit 获得 `test` check |
| release PR squash merge 后 main CI 成功 | 构建并推送 GHCR，再创建 GitHub Release/tag |
| commit message 与版本不匹配 | Publish 输出 skip，不生成发布资产 |
| `vX.Y.Z` 已存在 | Publish skip，重跑不覆盖版本 |
| GHCR push 失败 | tag/Release 尚未创建；修复后手动重跑 Publish |
| Web/Python 版本漂移 | Prepare 的 stamp script 将 Web version 同步到新版本 |
| Docker runtime 缺 migration 文件 | 应视为构建缺陷；应用启动时 Alembic 无法升级 |
| Compose 未设置或传入空 `DATABASE_URL` | 使用 Control Plane bind mount 目录中的 SQLite `/app/data/infinex.db` |
| Compose 设置外部 `DATABASE_URL` | Control Plane 直接连接该数据库；连接或 migration 失败时容器启动失败 |
| live worker 未设置 `CONTROL_PLANE_URL` 或 `LIVE_WORKER_ID` | Compose 插值失败，不启动配置不完整的远程 worker |
| bind mount 目录不存在或 UID/GID `10001` 不可写 | Compose/runtime 启动失败；先创建目录并修复宿主机权限 |
| PR image build 或 smoke test 失败 | 必需的 `test` check 失败，ruleset 阻止 merge |
| action 未 pin SHA | `zizmor`/review 失败，必须修复 |

### 5. Good/Base/Bad Cases

- Good：多个 `feat`/`fix` PR 以 Conventional title squash merge；维护者按批次运行 Prepare `auto`；release PR 通过 CI 并 squash merge；Publish 生成 changelog、正式 tag、Release 与 GHCR stable tags。
- Base：只有 docs/chore 且无版本 bump 时，Prepare `auto` 不创建 PR；普通 main CI 的 Publish guard 安全跳过。
- Bad：每个 feature PR merge 后自动推送 `main`/beta image，会产生大量无消费价值的镜像和版本噪音。
- Bad：Prepare 直接 push `main` 或直接创建 tag，绕过 release PR 和 `main` ruleset 审查。
- Bad：Publish 先创建 tag 再 build image；image 失败后会留下不可运行的正式版本。
- Bad：为同步 Web 版本引入 npm/package-lock；当前项目的包管理契约是 Bun。

### 6. Tests Required

Workflow/版本改动至少运行：

```bash
uvx zizmor .github/workflows
actionlint .github/workflows/*.yml
GIT_COMMIT_AUTHOR='semantic-release <semantic-release>' \
  uvx --from python-semantic-release==10.6.1 \
  semantic-release --noop version --no-push --no-vcs-release
uv run pytest -q tests/test_stamp_web_version.py
```

常规质量检查：

```bash
uv sync --extra dev --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
cd web
bun install --frozen-lockfile
bun run typecheck
bun test
bun run build
```

容器环境可用时：

```bash
docker build -t infinex:local .
docker compose config
CONTROL_PLANE_URL=https://infinex.example.com \
LIVE_WORKER_ID=live-node-01 \
  docker compose -f docker-compose.live-worker.yml config
docker compose up --build
curl -fsS http://127.0.0.1:8002/api/health
curl -fsS http://127.0.0.1:8002/
```

GitHub 上首次验证：

1. 普通 feature PR 的 `test` check 成功且只能 squash merge。
2. 手动运行 Prepare Release，确认 release PR 自动创建且显式 CI 成功。
3. squash merge release PR，确认 main CI 成功后 Publish 创建 GHCR、tag 和 GitHub Release。

### 7. Wrong vs Correct

#### Wrong

```yaml
on:
  push:
    branches: [main]

steps:
  - run: semantic-release version
```

问题：普通 merge 直接改版本、推 tag，绕过 release PR 和 `main` ruleset。

#### Correct

```yaml
on:
  workflow_dispatch:
    inputs:
      release_type:
        type: choice
```

原因：版本批次由维护者决定，生成的 changelog/version 先通过 PR 审查。

#### Wrong

```yaml
- uses: actions/checkout@v4
```

问题：可变 tag 不满足当前 supply-chain 契约。

#### Correct

```yaml
- uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5
  with:
    persist-credentials: false
```

原因：完整 SHA 可复现，且默认不把写入凭证留在 Git config。
