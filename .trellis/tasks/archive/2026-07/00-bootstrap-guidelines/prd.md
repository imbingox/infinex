# 初始化任务：补充项目开发规范

**你（AI）正在执行本任务，开发者通常不会直接阅读本文件。**

开发者刚在本项目首次运行 `trellis init`。`.trellis/` 已包含规范脚手架，
本任务位于 `.trellis/tasks/`。开始执行时，应使用能够提供 Trellis session identity
的会话启动本任务。

**你的工作**：帮助团队用真实编码约定补充 `.trellis/spec/`。未来 AI 会话中的
`trellis-implement` 与 `trellis-check` 审查代理会按任务 jsonl manifest 自动加载
对应规范。空规范会让代理生成通用代码；基于当前仓库事实的规范能让代理延续团队
已经落地的模式。

不要一次倾倒大量说明。先简短问候，确认仓库是否已有约定文档（例如 `CLAUDE.md`、
`.cursorrules`），再通过对话推进后续工作。

---

## 状态（完成后更新 checkbox）

- [x] 补充 backend 规范
- [x] 补充 frontend 规范
- [x] 补充 ops 规范
- [x] 添加真实代码示例
- [x] 添加项目级子代理委派规则

---

## 需要补充的文件

### Backend 规范

| 文件 | 记录内容 |
|------|----------|
| `.trellis/spec/backend/directory-structure.md` | route、service、utility 等文件的放置位置 |
| `.trellis/spec/backend/database-guidelines.md` | ORM、migration、查询模式与命名约定 |
| `.trellis/spec/backend/error-handling.md` | 错误如何捕获、记录与返回 |
| `.trellis/spec/backend/logging-guidelines.md` | 日志级别、格式与记录边界 |
| `.trellis/spec/backend/quality-guidelines.md` | Code review 标准与测试要求 |

### Frontend 规范

| 文件 | 记录内容 |
|------|----------|
| `.trellis/spec/frontend/index.md` | Frontend 范围、导航、开发前检查与质量检查 |
| `.trellis/spec/frontend/web-console-guidelines.md` | React/Vite 结构、API 边界、状态/UI 模式、测试与构建命令 |

### Ops 规范

| 文件 | 记录内容 |
|------|----------|
| `.trellis/spec/ops/index.md` | 仓库交付与运维范围、导航和检查项 |
| `.trellis/spec/ops/github-actions-guidelines.md` | 当前 CI trigger、service、toolchain、permission 与验证方式 |
| `.trellis/spec/ops/git-workflow-guidelines.md` | 提交卫生、Trellis bookkeeping 与安全历史操作 |

### 项目级代理规则

| 文件 | 记录内容 |
|------|----------|
| `AGENTS.md` | managed block 外的项目语言政策与子代理委派政策 |

### Thinking guides（已预填）

`.trellis/spec/guides/` 已包含通用 thinking guides。只有在内容明确不适合本项目时才定制。

---

## 如何补充规范

### 第一步：优先导入现有约定文件

搜索仓库中已有的约定文档。如果存在，先阅读并将相关规则提炼到对应的
`.trellis/spec/` 文件中，这通常比从零记录更高效。

| 文件或目录 | 工具 |
|------|------|
| `CLAUDE.md` / `CLAUDE.local.md` | Claude Code |
| `AGENTS.md` | Codex / Claude Code / 兼容 agent 的工具 |
| `.cursorrules` | Cursor |
| `.cursor/rules/*.mdc` | Cursor rules 目录 |
| `.windsurfrules` | Windsurf |
| `.clinerules` | Cline |
| `.roomodes` | Roo Code |
| `.github/copilot-instructions.md` | GitHub Copilot |
| `.vscode/settings.json` 中的 `github.copilot.chat.codeGeneration.instructions` | VS Code Copilot |
| `CONVENTIONS.md` / `.aider.conf.yml` | aider |
| `CONTRIBUTING.md` | 通用项目约定 |
| `.editorconfig` | 编辑器格式约定 |

### 第二步：分析现有文档未覆盖的代码事实

扫描真实代码以发现模式。编写每份规范前：

- 为每种模式找到 2 至 3 个真实代码示例。
- 引用真实文件路径，不使用假设路径。
- 记录代码明确避免的反模式。

### 第三步：记录现实，而不是理想

**关键要求**：记录代码当前实际采用的方式，而不是未来应该采用的方式。子代理会匹配
规范，因此不存在的理想模式会让后续代码偏离仓库现状。

如果团队存在已知技术债，记录当前状态；改进方案应作为独立讨论或任务处理。

---

## Runtime 简介（开发者询问“为什么需要 spec”时使用）

- 每个 AI 编码任务会使用 `trellis-implement`（实现）和 `trellis-check`（验证）角色。
- 每个任务的 `implement.jsonl` / `check.jsonl` manifest 会列出需要加载的 spec 文件。
- 平台 hook 会把这些 spec 与任务 `prd.md` 自动注入代理 prompt，使代理无需人工粘贴也能遵循团队约定。
- `.trellis/spec/` 是规范事实来源，因此首次完整补充能持续改善后续任务质量。

---

## 完成方式

确认以上 checkbox 均已由真实示例支撑且不存在 placeholder 后，引导开发者运行：

```bash
python3 ./.trellis/scripts/task.py finish
python3 ./.trellis/scripts/task.py archive 00-bootstrap-guidelines
```

归档后，新加入本项目的开发者会收到 `00-join-<slug>` onboarding task，而不是本 bootstrap task。

---

## 建议开场白

“欢迎使用 Trellis！初始化已经完成。接下来我会帮你一次性补全项目规范，让未来 AI 会话
遵循团队现有约定，而不是生成通用代码。仓库里是否已有 `CLAUDE.md`、`.cursorrules`、
`CONTRIBUTING.md` 等约定文档可供导入，还是需要我直接从当前代码开始分析？”
