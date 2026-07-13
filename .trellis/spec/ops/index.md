# 仓库交付与发布规范

> 本目录记录 Infinex 当前已经落地的 GitHub Actions CI、正式发布、GHCR/容器与 Git/Trellis 提交流程。

## 适用范围

- 三个 GitHub Actions workflow 的触发条件、权限、版本 guard 与发布顺序。
- `pyproject.toml`、`CHANGELOG.md` 与 Web version stamping 的 semantic-release 契约。
- `Dockerfile`、`.dockerignore`、`docker-compose.yml` 与 GHCR tags。
- PR title、squash merge、`main` ruleset、提交分组、dirty worktree 保护和 Trellis 收尾顺序。

Python 代码质量细节仍以 `../backend/quality-guidelines.md` 为准；前端构建与静态托管以 `../frontend/web-console-guidelines.md` 为准。

## 规范索引

| Guide | 内容 | 状态 |
|-------|------|------|
| [GitHub Actions、正式发布与 GHCR 规范](./github-actions-guidelines.md) | CI、release PR、semantic-release、Docker/GHCR、仓库保护与验证 | 已填 |
| [Git 工作流规范](./git-workflow-guidelines.md) | Conventional PR/commit、squash merge、精确暂存、Trellis 顺序与历史安全 | 已填 |

## 开发前检查

- [ ] 先运行 `git status --short`，区分本任务文件、用户已有改动和其他会话的改动。
- [ ] 修改 workflow 前同时核对三个 workflow、`pyproject.toml`、`CHANGELOG.md`、版本脚本、Dockerfile 与 Web/Python lockfile，避免 guard 或版本来源漂移。
- [ ] 修改 release commit message、tag format、PR title 任一项时，全仓搜索并同步 semantic-release、Prepare、Publish 和 ruleset/merge 文档。
- [ ] Dockerfile 中改动 Web 产物、migration 或运行目录时，同时核对 FastAPI settings、Compose environment 和 README。
- [ ] 涉及 PostgreSQL 测试时确认 `TEST_POSTGRES_URL` 指向一次性测试数据库。
- [ ] 提交前从近期历史学习 message 风格，并只规划本轮实际修改的文件。

## 质量检查

纯 ops spec 改动至少检查：

```bash
git diff --check -- .trellis/spec/ops
git status --short
```

修改 CI/release 后还应检查 workflow 与版本配置，并按 CI 顺序运行对应命令：

```bash
git diff --check -- .github/workflows .trellis/spec/ops
uvx zizmor .github/workflows
uv sync --extra dev --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
cd web && bun install --frozen-lockfile && bun run typecheck && bun test && bun run build
# GitHub CI 还会执行 Docker image build + container smoke test
```

本地没有一次性 PostgreSQL 时，不能把未设置 `TEST_POSTGRES_URL` 的测试结果描述为 PostgreSQL 路径已验证；没有 Docker daemon 时，也不能把 Compose 静态解析描述为 image runtime 已验证。完整契约见 [GitHub Actions、正式发布与 GHCR 规范](./github-actions-guidelines.md)。

## 维护原则

规范正文使用中文，路径、命令、环境变量和 action 名称保留源码原文。更新本目录时以三个 workflow、manifest/lockfile、容器文件、GitHub API 返回的仓库设置、`.trellis/workflow.md` 和实际 Git 历史为证据；旧仓库流程不能直接升级为当前项目约定。
