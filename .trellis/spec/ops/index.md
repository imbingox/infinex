# 仓库交付规范

> 本目录记录 Infinex 当前已经落地的 GitHub Actions CI 与 Git/Trellis 提交流程。规范只描述仓库现状及其安全修改方式，不扩展到尚不存在的发布或镜像流程。

## 适用范围

- `.github/workflows/ci.yml` 的触发条件、运行环境、服务依赖和质量命令。
- 根目录 `pyproject.toml`、`uv.lock` 与 `web/package.json`、`web/bun.lock` 对 CI 安装和检查命令的约束。
- Git 提交分组、dirty worktree 保护、历史操作安全和 Trellis 收尾提交顺序。

Python 代码质量细节仍以 `../backend/quality-guidelines.md` 为准；本目录只记录 CI 如何调用这些检查。当前仓库没有可作为规范依据的 release workflow、Docker/GHCR 发布或自动版本流程。

## 规范索引

| Guide | 内容 | 状态 |
|-------|------|------|
| [GitHub Actions 规范](./github-actions-guidelines.md) | 当前 CI 事实、frozen install、backend/web checks 与修改验证 | 已填 |
| [Git 工作流规范](./git-workflow-guidelines.md) | Conventional Commit、精确暂存、Trellis 提交顺序与历史安全 | 已填 |

## 开发前检查

- [ ] 先运行 `git status --short`，区分本任务文件、用户已有改动和其他会话的改动。
- [ ] 修改 `.github/workflows/ci.yml` 前同时核对 `pyproject.toml`、`uv.lock`、`web/package.json` 与 `web/bun.lock`，不要让 CI 命令脱离 manifest/lockfile。
- [ ] 确认需求属于现有 CI 或 Git 工作流；新增发布、镜像、tag 或远端仓库策略属于新的设计范围，不能从本规范推断。
- [ ] 涉及 PostgreSQL 测试时确认 `TEST_POSTGRES_URL` 指向一次性测试数据库。
- [ ] 提交前从近期历史学习 message 风格，并只规划本轮实际修改的文件。

## 质量检查

纯 ops spec 改动至少检查：

```bash
git diff --check -- .trellis/spec/ops
git status --short
```

修改 CI 后还应检查 workflow diff，并按 CI 顺序运行对应命令：

```bash
git diff --check -- .github/workflows/ci.yml
uv sync --extra dev --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
cd web && bun install --frozen-lockfile && bun run typecheck && bun test && bun run build
```

本地没有一次性 PostgreSQL 时，不能把未设置 `TEST_POSTGRES_URL` 的测试结果描述为 PostgreSQL 路径已验证。完整 CI 事实和按改动验证方法见 [GitHub Actions 规范](./github-actions-guidelines.md)。

## 维护原则

规范正文使用中文，路径、命令、环境变量和 action 名称保留源码原文。更新本目录时以 `.github/workflows/ci.yml`、manifest/lockfile、`.trellis/workflow.md`、Trellis 脚本和实际 Git 历史为证据；暂态工作区内容和旧仓库流程不能升级为项目约定。
