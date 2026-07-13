# Git 工作流规范

> 本规范依据当前 Git 历史、`.trellis/workflow.md`、Trellis 收尾脚本和 ignore 配置，约束提交信息、dirty worktree 保护与安全历史操作。

## 当前历史风格

当前可见历史只有两个提交：

```text
bea0eef fix: stabilize CI and database bootstrap
0a499dc feat: implement stage one control plane
```

可确认的本地模式是 Conventional Commit 前缀、英文简短 summary、前缀后使用冒号和空格。样本很少，因此不要从这两条记录推断固定 branch naming、merge strategy、scope 清单或 branch protection。

提交信息使用：

```text
<type>[optional scope]: <summary>
```

- 行为能力使用 `feat:`，缺陷修复使用 `fix:`，与现有历史一致。
- workflow 变更可使用 `ci:`，纯规范变更可使用 `docs(spec):`；这是按 Conventional Commit 语义选择 type，不表示历史中已经出现过这些前缀。
- summary 保持英文、简短并描述实际动作；避免 `update files`、`misc changes` 等无法判断意图的表述。
- `scope` 只有在边界明确且确实提高可读性时使用，不为追求格式强行添加。

## 提交分组与精确暂存

一个 work commit 应表达一个可独立理解的逻辑变更。workflow、产品代码、无关文档和 Trellis bookkeeping 不应因为同时出现在 worktree 就合并进同一提交。

提交前按以下顺序检查：

```bash
git status --short
git diff --stat
git diff --check
git diff --cached --stat
git diff --cached --name-only
```

- 先记录所有 dirty path，再区分本轮修改、用户已有修改和其他会话的并行工作。
- 使用 `git add <明确路径>` 或等价的精确选择，只暂存已经审阅并属于该逻辑提交的文件。
- 不使用 `git add .`、`git add -A` 把未识别文件整体纳入。
- commit 前再次核对 cached file list；发现未知文件时先移出当前计划并询问所有者，不猜测归属。
- 未跟踪文件不会出现在普通 `git diff` 中，必须结合 `git status --short` 和文件内容单独审阅。

## Dirty worktree 保护

仓库可能同时存在用户手工改动、其他终端任务和 Trellis 运行态文件。任何自动化或 AI 会话都必须保留不属于当前任务的变更。

根 `.gitignore` 已排除 `.env` 与 `.env.*`（保留 `.env.example`）、`data/`、cache、虚拟环境、`node_modules/` 和 build output；`.trellis/.gitignore` 已排除 developer identity、session runtime、current-task pointer、agent runtime、临时文件与 cache。不要使用 `git add -f` 绕过这些边界，除非用户明确要求提交某个已审查文件。

遇到 dirty worktree 时：

1. 不清理、不回滚、不覆盖未知改动。
2. 只编辑任务授权范围内的文件；若目标文件本身已有未知修改，先停下来确认。
3. 验证和提交命令使用明确路径，避免全仓格式化或批量暂存扩大影响面。
4. 交付时报告仍存在但未触碰的 dirty path，不把它们描述为本轮产物。

## Trellis 工作、归档与 journal 顺序

`.trellis/workflow.md` 要求先完成实现、全范围质量检查和必要的 spec 更新，再进入 Phase 3.4 创建 work commits。之后由 finish-work 流程归档任务并记录 session：

```text
<work commit(s)>
chore(task): archive <task>
chore: record journal
```

具体约束：

- work commits 必须先完成，不能把未提交的任务代码留给 finish-work。
- `task.py archive <task>` 将任务标记完成并移入 archive；当前默认行为会生成 `chore(task): archive ...` 提交。
- `add_session.py --commit "<work hashes>" ...` 最后记录 journal；传入的是 work commit hash，不包含 archive commit hash。
- `.trellis/config.yaml` 当前 journal commit message 为 `chore: record journal`。
- archive 和 journal 提交不能插在 work commits 中间，也不应与产品或规范改动合并。

本规范任务若只负责实现文件，不应擅自执行 archive、journal 或 commit；这些动作由主会话按 Trellis 阶段和用户确认完成。

## 历史操作安全

- 常规流程只创建新 commit，不使用 `git commit --amend`。
- 不运行 `git reset --hard`、`git checkout -- <path>`、未经确认的 rebase/reword 或 force push。
- 不自动 push；远端写入必须来自明确需求。
- 已共享或已 push 的历史默认不可重写。确需重写时，必须先获得明确授权，说明受影响 commit 和 force push 风险，并确认 dirty worktree 已隔离。
- 本地历史重写会改变 hash；若 Trellis task、journal 或其他文档已经引用旧 hash，必须同步检查引用是否失效。
- 当前仓库没有可证明的 branch protection、强制 PR 或 merge strategy 约定，本规范不替 GitHub 仓库设置作出假设。

## 按改动验证

纯 spec/Git 文档变更至少运行：

```bash
git diff --check -- .trellis/spec/ops
git status --short
```

workflow 变更按 [GitHub Actions 规范](./github-actions-guidelines.md) 运行 backend/Web 对应检查。产品代码提交还需加载受影响 package 的 spec index，并完成其中 Quality Check；不要用 Git 提交成功代替 lint、test 或跨层验证。

## 禁止模式

- 把未知 dirty files 静默放进当前 commit。
- 用一个含糊 commit 同时提交 work、task archive 和 journal。
- 因为文件被 ignore 就把 credential、数据库、cache 或 runtime 强制加入版本控制。
- 在没有仓库证据时宣称必须 squash、必须使用某个 branch 名或已经启用 branch protection。
