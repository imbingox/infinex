# 数据库规范

> 当前持久化使用 SQLModel/SQLAlchemy，运行时支持 SQLite 与 PostgreSQL，schema 变更统一由 Alembic 管理。

## 数据库入口

核心文件：

- `src/infinex/control_plane/models.py`：表模型、状态枚举、ID 与 UTC helper。
- `src/infinex/control_plane/db.py`：惰性全局 Engine、FastAPI Session dependency、Alembic upgrade。
- `migrations/env.py`：读取 `SQLModel.metadata` 与 `Settings.database_url`。
- `migrations/versions/20260710_0001_initial_schema.py`：当前初始 schema。

默认 URL 是 `sqlite:///data/infinex.db`。SQLite Engine 开启 `check_same_thread=False`，并在 connect event 中执行 `PRAGMA foreign_keys=ON`；其它 URL 使用 `pool_pre_ping=True`。这些分支集中保留在 `get_engine()`。

## Model 约定

- 表实体继承 `SQLModel, table=True`；API-only request shape 使用 `schemas.py` 的 `BaseModel`，不创建伪表。
- 主键是带领域前缀的字符串，例如 `strat_`、`sv_`、`bt_`、`dep_`，统一调用 `new_id()`。
- 所有新时间戳使用 `utc_now()`；可变实体在状态改变时同步维护 `updated_at`。
- 外键使用 `Field(foreign_key="<table>.<column>")`，常用查询字段明确 `index=True`。
- 稳定唯一性使用命名 `UniqueConstraint`，例如 `uq_strategy_name` 与 `uq_command_message_id`。
- 灵活 payload/result 使用 SQLAlchemy `JSON` column；大段源码使用 `Text`。Python 属性与列名不同时显式映射，例如 `Worker.metadata_json` -> 数据库列 `metadata`。
- 状态枚举继承 `StrEnum`，数据库字段当前存 `.value` 字符串，不依赖数据库 enum type。

示例来自 `Worker`：

```python
metadata_json: dict[str, Any] = Field(
    default_factory=dict,
    sa_column=Column("metadata", JSON),
)
```

不要直接暴露含 `credential_hash` 的 ORM 内容；`Worker.credential_hash` 设置了 `exclude=True`，API 进一步通过 `worker_view()` 白名单返回字段。

## Session 与事务所有权

FastAPI route 使用 `SessionDep = Annotated[Session, Depends(get_session)]`。领域 service 接收现有 `Session`，负责查询、`session.add()`、状态转换和 audit，但正常写路径由 route 统一提交：

```python
session.flush()          # 仅在 commit 前需要生成 ID/约束结果时
audit(session, ...)
commit(session)          # IntegrityError -> rollback + HTTP 409
session.refresh(entity)
await publish_update(...)
```

重要规则：

- 一个业务动作及其 `AuditEvent` 在同一事务提交。
- `publish_update()` 在 commit 之后调用，避免消费者看到尚未持久化的状态。
- 只有 route/显式后台工作单元提交；不要在深层 helper 中隐藏 commit，当前 service 函数不拥有事务终点。
- 测试 fixture 可使用 `SQLModel.metadata.create_all()` 创建内存 SQLite；运行时和生产/共享数据库必须使用 Alembic。
- 后台 sweep 在 `maintenance.py` 中显式创建 `Session(get_engine())`，只有状态真的改变才 commit。

## 查询约定

当前查询使用 SQLModel 的 `select()` 与 `session.exec()`：

```python
statement = select(Command).where(
    Command.worker_id == worker_id,
    Command.status.in_([CommandStatus.PENDING.value, CommandStatus.ACKED.value]),
)
commands = session.exec(statement.order_by(Command.created_at)).all()
```

- 通过主键读取使用 `session.get(Model, id)`；需要统一 HTTP 404 时调用 `services.get_or_404()`。
- 列表端点明确稳定排序；提供 `limit` 的端点（当前为 Command 与 AuditEvent 列表）用 `Query` 限制范围。不要给新增的大结果集留下无界查询。
- 关联一致性不只依赖外键：例如 ConfigVersion 与 StrategyVersion 的配对、Worker role、runtime compatibility 由 service/route 显式检查并返回 409。

## Alembic migration

`uv run infinex init-db` 调用 `init_db()`，再执行 `alembic upgrade head`。表结构变更必须：

1. 修改 `models.py`。
2. 新增 `migrations/versions/<revision>_<description>.py`，填写 upgrade 和可逆 downgrade。
3. 保留 index、unique constraint、foreign key 和 column nullability 与 model 一致。
4. 先在全新 SQLite 数据库跑完整测试，再通过 `TEST_POSTGRES_URL` 运行真实 PostgreSQL migration test。

验证命令：

```bash
uv run pytest
TEST_POSTGRES_URL='postgresql+psycopg://...' uv run pytest -m postgres
```

`tests/test_postgres_integration.py` 是 PostgreSQL migration + round-trip 的参考；没有该环境变量时 marker 会 skip。

## 常见错误

- 不要在运行时用 `metadata.create_all()` 代替 migration；这无法升级已有数据库。
- 不要发出通知后才 commit，或把 audit 放在另一个事务。
- 不要在多个模块各自创建 Engine；通过 `get_engine()`，测试隔离时用 dependency override/reset helper。
- 不要用无时区时间参与 heartbeat lease、状态 sweep 或运行历史。
- 不要只在 SQLite 验证 migration；当前 CI 明确以 PostgreSQL 17 运行数据库路径。
