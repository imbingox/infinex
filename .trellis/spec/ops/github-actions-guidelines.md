# GitHub Actions 规范

> `.github/workflows/ci.yml` 是当前唯一 workflow。本规范先记录它现在做什么，再单独列出修改时应执行的检查。

## 当前 CI 拓扑

| 项目 | 当前事实 |
|------|----------|
| Workflow | `CI`，文件为 `.github/workflows/ci.yml` |
| Trigger | `push` 与 `pull_request`，没有 branch 或 path filter |
| Job | 单一 `test` job |
| Runner | `ubuntu-latest` |
| Service | `postgres:17`，映射 `5432:5432`，用 `pg_isready` 做 health check |
| Python setup | `astral-sh/setup-uv@v6`，`enable-cache: true` |
| Web setup | `oven-sh/setup-bun@v2`，`bun-version: latest` |
| Checkout | `actions/checkout@v4` |

当前 `uses:` 都引用 version tag，不是完整 commit SHA；`ubuntu-latest` 与 `bun-version: latest` 也会随上游变化。只能把它们记录为现状，不能宣称 runner、Bun 或 actions 已固定到不可变版本。

## PostgreSQL 与测试环境

CI 为 PostgreSQL service 设置：

- database：`infinex_test`
- user/password：`infinex` / `infinex`
- health check：`pg_isready -U infinex -d infinex_test`
- job 环境变量：`TEST_POSTGRES_URL=postgresql+psycopg://infinex:infinex@127.0.0.1:5432/infinex_test`

`pyproject.toml` 将 `postgres` marker 定义为需要一次性 PostgreSQL 的测试。CI 提供上述数据库，因此 `uv run pytest -q` 可以执行 PostgreSQL migration/round-trip 路径；本地若未设置 `TEST_POSTGRES_URL`，该路径允许 skip。

CI 还设置测试用 `WORKER_ENROLLMENT_TOKEN=ci-enrollment-token`。这些值只属于隔离的 CI 测试环境，不得替换为开发或生产 credential，也不得复用于持久数据库。

## 安装与检查顺序

Backend 安装使用：

```bash
uv sync --extra dev --frozen
```

`--frozen` 要求安装与根目录 `uv.lock` 一致，CI 不在运行中重新解析并改写 lockfile。随后执行：

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

`pyproject.toml` 的 Ruff 配置排除 `.claude/`、`.codex/` 与 `.trellis/`。因此上述全仓命令检查产品 Python、tests 与 migration，但不把 Trellis 生成的跨平台 hook/runtime 脚本当作本项目源码重新格式化。

Web 步骤的 `working-directory` 是 `web`，安装使用：

```bash
bun install --frozen-lockfile
```

该命令要求 `web/bun.lock` 与 `web/package.json` 一致。随后按当前 workflow 的显式顺序执行：

```bash
bun run typecheck
bun test
bun run build
```

`web/package.json` 中 `build` 本身还会运行 `tsc --noEmit && vite build`；不要因为存在这层重复就擅自删除 CI 的独立 `typecheck` 步骤，除非改动目标明确要求调整检查契约。

## 修改 workflow 的规则

- CI 命令应与 `pyproject.toml`、`web/package.json` 中真实存在的工具和 script 保持一致；不要引入旧项目的 pyright、npm 或其他未配置命令。
- 保持 frozen install。依赖变更应在本地更新对应 manifest 与 lockfile，再让 CI 验证；不要在 CI 中生成新的 lockfile。
- PostgreSQL service、health check 与 `TEST_POSTGRES_URL` 必须一起审查。修改 database/user/port 中任一项时，同步更新连接 URL 和 health check。
- Backend 与 Web 检查目前在同一个 job 内顺序执行。拆分 job、增加 matrix 或改变失败边界属于 workflow 行为变更，需要明确说明，不应当作纯格式调整。
- 当前 workflow 没有发布、tag、GitHub Release、Docker 或 GHCR 步骤。增加这些能力需要独立需求与设计，不能附带塞入普通 CI 修改。
- 安全审查可以建议把 action 改为完整 SHA、把工具链版本改为固定版本；在 workflow 真正完成相应修改前，规范必须继续把 tag/`latest` 写成当前事实。

## 修改检查：建议项而非当前 CI step

以下命令用于修改后的本地核对，它们不是 `.github/workflows/ci.yml` 中新增的 step：

```bash
git diff --check -- .github/workflows/ci.yml
git diff -- .github/workflows/ci.yml
rg -n 'push:|pull_request:|ubuntu-latest|postgres:17|TEST_POSTGRES_URL|setup-uv@|setup-bun@|--frozen|--frozen-lockfile|ruff check|pytest -q|typecheck|bun test|bun run build' .github/workflows/ci.yml
```

如果改动触及 backend 安装或检查，运行：

```bash
uv sync --extra dev --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

如果改动触及 Web 安装或检查，运行：

```bash
cd web
bun install --frozen-lockfile
bun run typecheck
bun test
bun run build
```

若本地提供一次性 PostgreSQL，再使用与该数据库匹配的 `TEST_POSTGRES_URL` 运行 pytest；否则报告中应明确 PostgreSQL 路径只由 GitHub Actions 环境覆盖。workflow 在 GitHub 上实际运行成功，才是 runner、service container、cache 和 setup action 组合的最终验证。

## 禁止模式

- 不得把 dependency install 的 frozen 状态等同于 action、runner 或 Bun 版本已 pin。
- 不得只改 `TEST_POSTGRES_URL` 而遗漏 service credential、port 或 health check。
- 不得把本地未执行 PostgreSQL marker 的 pytest 结果表述为完整 CI 等价验证。
- 不得复制不存在的 release、Docker、GHCR、semantic-release 或 branch policy 流程到本规范。
