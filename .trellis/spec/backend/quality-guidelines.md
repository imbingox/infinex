# 后端质量规范

> `pyproject.toml` 与 `.github/workflows/ci.yml` 是质量命令的当前来源；不要沿用旧仓库的 pyright、npm 或 Redis 测试命令。

## 工具基线

- Python `>=3.13`，依赖与命令统一通过 `uv`。
- Ruff line length 为 100、target 为 `py313`，规则集为 `E`、`F`、`I`、`UP`、`B`。
- Ruff 排除 Trellis 生成的 `.claude/`、`.codex/` 与 `.trellis/` Python 运行文件；这些文件由 Trellis 模板维护，不属于产品源码质量边界。
- pytest 测试根目录是 `tests/`，`src` 通过 pytest `pythonpath` 加载。
- `postgres` marker 需要指向一次性数据库的 `TEST_POSTGRES_URL`；未设置时允许 skip。

后端完整检查：

```bash
uv sync --extra dev --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

开发中可以先跑最小相关测试，但交付前应回到完整命令。CI 还会启动 PostgreSQL 17 并设置 `TEST_POSTGRES_URL`。

## 代码约定

- 公开边界普遍使用 Python 3.13 类型注解；协议 payload 等异构容器使用 `dict[str, Any]`，抽象迭代器从 `collections.abc` 导入。`services.py` 仍有少量历史裸 `dict` 注解；新增或修改边界应使用参数化类型，不要继续扩散该写法。
- API 输入优先用 Pydantic model，不在 route 中手动解析未经类型化的 dict。
- 状态拼写来自 `StrEnum.value`；跨层 payload 需要检查 Python schema、SQLModel、Worker client 和 TypeScript DTO。
- 同一行为只保留一个 helper：实体 404 用 `get_or_404()`、commit 冲突用 `api.commit()`、token 校验用 `security.py`、Control Plane HTTP 用 `ControlPlaneClient`。
- 外部副作用显式放在边界：数据库 commit、Socket.IO emit、文件写入与 subprocess 不隐藏在纯 hash/状态计算 helper 中。
- HTTP client 和 Socket.IO client 在 Worker 的 `finally` 中关闭；Runner 的进程与日志文件由 Worker 生命周期边界管理。Live Runner 被设计为在 Control Plane 断开期间继续运行，不要因连接丢失而清理它；显式停止 Runner 时则必须按 `terminate`/超时 `kill` 的路径回收进程并关闭日志文件。Backtest subprocess 使用有界 timeout。

## 测试分层

| 层级 | 当前参考 | 适用改动 |
|------|----------|----------|
| 纯函数/单元 | `tests/test_runner.py`、`tests/test_logging.py`、`tests/test_worker_status.py` | hash、formatter、状态计算、确定性输出 |
| API 工作流 | `tests/test_api_workflow.py` | route、schema、service、auth、audit、状态转换 |
| 进程集成 | `tests/test_process_integration.py` | CLI server、Agent、Runner、Socket.IO 重连、信号、凭据文件 |
| 数据库集成 | `tests/test_postgres_integration.py` | Alembic 与 PostgreSQL-specific 行为 |

`tests/conftest.py` 用 dependency override 注入内存 SQLite Session，并用临时 artifact directory 隔离文件。新增 API test 应复用 `client`、`session`、`worker_headers`，不要连接开发数据库。

需要真实进程的测试遵循现有 helper：动态申请端口、用 `wait_until()` 有界轮询、在 fixture/finally 中 terminate 后必要时 kill。不要用固定 sleep 作为唯一同步，也不要遗留 Runner 进程。

## 按改动选择验证

- API/schema/service：`uv run pytest tests/test_api_workflow.py`
- 日志/middleware：`uv run pytest tests/test_logging.py tests/test_api_workflow.py`
- Runner/bundle：`uv run pytest tests/test_runner.py`
- Worker 状态：`uv run pytest tests/test_worker_status.py tests/test_process_integration.py`
- migration/model：完整 pytest + 配置 `TEST_POSTGRES_URL` 的 postgres marker
- CLI 命令：除相关测试外，至少运行 `uv run infinex --help` 和改动命令的 `--help`
- 同时改 `web/` 或 API response：再运行 `cd web && bun run typecheck && bun test && bun run build`

## Review 检查表

- [ ] route -> service/model -> commit -> notify 顺序正确，audit 与状态在同一事务。
- [ ] desired/actual state、revision、generation、lease 的转换可恢复且重复调用安全。
- [ ] Socket.IO 仍只是唤醒提示，HTTP/数据库同步路径可以独立收敛。
- [ ] Worker token、artifact SHA-256、runtime compatibility 和对象所有权未被绕过。
- [ ] 错误状态码可解释，后台失败会记录并重试，取消/进程停止能清理资源。
- [ ] 新表/列有 migration；SQLite 与 PostgreSQL 差异已验证。
- [ ] 测试能在临时目录/动态端口运行，不依赖本机持久状态。
- [ ] README、`.env.example`、Web DTO 或命令说明在公共契约变化后同步。

## 禁止模式

- 禁止用 `# noqa`、宽泛 skip 或降低 Ruff 规则掩盖新问题。当前局部例外只有：`tests/conftest.py` 为先设置环境变量再导入 app 使用 `E402`，`migrations/env.py` 为注册 SQLModel metadata 使用 `F401`。
- 禁止把真实 token/credential 写入 fixture、日志或 snapshot。
- 禁止只测试自己重写的同一计算，形成不会因实现回归而失败的同义测试。
- 禁止让单元测试使用真实 `data/infinex.db`、固定服务端口或用户工作目录。
- 禁止仅运行 SQLite 测试就宣称 migration 已跨数据库验证。
