# 后端开发规范

> 本目录记录当前 Infinex Python 后端已经落地的边界与约定；未来实现应先与现有代码和测试保持一致。

## 适用范围

后端包括 `src/infinex/`、`migrations/`、`tests/` 与根目录 Python 工具配置。当前运行时由以下部分组成：

- FastAPI + Socket.IO Control Plane：`src/infinex/control_plane/`
- Typer CLI：`src/infinex/cli.py`
- Live/Backtest Worker：`src/infinex/worker/`
- 独立 Runner 进程：`src/infinex/runner/`
- SQLModel 模型与 Alembic migration：`src/infinex/control_plane/models.py`、`migrations/`

## 规范索引

| Guide | 内容 | 状态 |
|-------|------|------|
| [目录与架构](./directory-structure.md) | 包边界、控制流、文件放置 | 已填 |
| [数据库规范](./database-guidelines.md) | SQLModel、Session、事务、Alembic | 已填 |
| [错误处理](./error-handling.md) | HTTP、Worker、后台循环与 Runner 错误 | 已填 |
| [日志规范](./logging-guidelines.md) | JSON 日志、request id、事件字段与敏感信息 | 已填 |
| [质量规范](./quality-guidelines.md) | Ruff、pytest、集成测试与跨层检查 | 已填 |

## 开发前检查

- [ ] 先阅读与改动相关的本目录规范；跨到 `web/` 时同时核对 `web/src/types.ts`、`web/src/api.ts` 与 `web/package.json`。
- [ ] 找到现有入口和相邻测试，不在 route、worker、runner 中重复已有 service/client 能力。
- [ ] 涉及状态机时列出持久化状态、允许转换、幂等行为和失败恢复路径。
- [ ] 涉及 API payload 时同步检查 `schemas.py`、`web/src/types.ts` 和调用方。
- [ ] 涉及表结构时同时设计 SQLModel model、Alembic migration 和 PostgreSQL 验证。

## 质量检查

常规后端改动至少运行：

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

数据库 migration 需要设置一次性 `TEST_POSTGRES_URL` 运行 `postgres` marker；进程、Worker、Socket.IO 或 Runner 生命周期改动应运行 `tests/test_process_integration.py`。完整要求见 [质量规范](./quality-guidelines.md)。

## 维护原则

规范正文使用中文，技术标识保持源码原文。更新时只记录当前仓库可由源码、测试、`README.md` 或 `docs/project-plan.md` 当前实现快照证明的事实；规划中的 NautilusTrader runner、生产鉴权等能力在落地前不是编码约定。
