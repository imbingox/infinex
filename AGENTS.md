<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

This project is managed by Trellis. The working knowledge you need lives under `.trellis/`:

- `.trellis/workflow.md` — development phases, when to create tasks, skill routing
- `.trellis/spec/` — package- and layer-scoped coding guidelines (read before writing code in a given layer)
- `.trellis/workspace/` — per-developer journals and session traces
- `.trellis/tasks/` — active and archived tasks (PRDs, research, jsonl context)

If a Trellis command is available on your platform (e.g. `/trellis:finish-work`, `/trellis:continue`), prefer it over manual steps. Not every platform exposes every command.

If you're using Codex or another agent-capable tool, additional project-scoped helpers may live in:
- `.agents/skills/` — reusable Trellis skills
- `.codex/agents/` — optional custom subagents

Managed by Trellis. Edits outside this block are preserved; edits inside may be overwritten by a future `trellis update`.

<!-- TRELLIS:END -->

## Project Language Policy

- 与用户交流时默认使用中文。
- 编写给人阅读的项目文档时默认使用中文，包括但不限于 `prd.md`、task 相关说明、设计文档、review 结论、session journal。
- 技术术语、命令、代码标识符、API 名称可以保留英文。
- 如果用户明确要求英文，再切换语言；否则默认保持中文。

## Sub-agent Delegation Policy

- 需要委派独立子任务时，优先使用 CodeG MCP 提供的 `delegate_to_agent` 与 `get_delegation_status`。
- 不使用 Codex 原生 `spawn_agent`，除非 CodeG 委派工具不可用，或用户明确要求使用 Codex 原生子代理。
- CodeG 子代理是冷启动独立会话，委派 prompt 必须自包含，明确工作目录、任务目标、背景、相关文件、读写范围、验证命令和返回格式。
- 并行委派时，为每个子代理划分互不重叠的写入范围；同一文件默认只允许一个代理修改。
- 子代理返回后，主会话负责核对事实、整合改动并执行最终质量检查。
