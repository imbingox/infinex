# 目录与架构规范

> 当前项目是 Python 3.13 `src` layout 单包项目，使用 `uv` 管理 Python 环境；Web Console 是独立的 `web/` Bun/Vite 子目录。

## 当前布局

```text
src/infinex/
├── cli.py                 # Typer 命令与进程装配
├── control_plane/
│   ├── app.py             # FastAPI/Socket.IO app、lifespan、静态 Web 托管
│   ├── api.py             # /api route、依赖注入、事务提交、通知
│   ├── schemas.py         # Pydantic 请求模型
│   ├── services.py        # 领域状态转换、查询、审计事件
│   ├── models.py          # SQLModel 表、状态枚举、ID/UTC helper
│   ├── db.py              # Engine、Session dependency、Alembic upgrade
│   ├── artifacts.py       # 确定性 JSON/hash 与策略 bundle
│   ├── realtime.py        # Socket.IO 鉴权、房间与轻量通知
│   ├── maintenance.py     # Worker 离线状态后台收敛
│   ├── logging.py         # JSON formatter 与 HTTP middleware
│   ├── security.py        # Worker token 生成、hash、constant-time verify
│   └── settings.py        # pydantic-settings 环境配置
├── worker/
│   ├── client.py          # Worker 到 Control Plane 的 HTTP client
│   ├── agent.py           # Live desired-state reconciliation 与子进程管理
│   └── backtest.py        # Backtest claim、bundle 校验与 Runner 调用
└── runner/
    ├── __main__.py        # `python -m infinex.runner` 命令边界
    └── mock.py            # 当前确定性 mock runner
migrations/                # Alembic env 与版本脚本
tests/                     # pytest 单元、API、真实进程与 PostgreSQL 测试
web/                       # React/Vite Console；是 API DTO 与实时通知的跨层消费者
```

证据：`pyproject.toml` 的 wheel package 是 `src/infinex`，命令入口是 `infinex.cli:app`；`README.md` 描述当前 mock runner 会在协议稳定后被替换。

## Control Plane 分层

新功能按职责放置：

- 外部请求的字段、范围和 `Literal` 校验放在 `control_plane/schemas.py`。例如 `WorkerRegister.capacity` 使用 `Field(ge=1, le=128)`。
- HTTP header、依赖注入、状态码、`commit()`、response 和 commit 后通知放在 `control_plane/api.py`。
- 可由 route 或后台任务复用的领域转换放在 `control_plane/services.py`。例如 `create_deployment_command()` 同时推进 desired revision、创建 `Command` 并追加 audit。
- 持久化 shape、状态枚举、ID 和 UTC 时间放在 `control_plane/models.py`。
- 文件 bundle/hash 放在 `artifacts.py`，凭据 hash/verify 放在 `security.py`；不要把这些逻辑复制到 route。

典型写路径如下：

```text
Pydantic payload -> API route -> service/model mutation -> audit
                 -> session commit -> session refresh -> Socket.IO notification
```

`publish_update()` 必须是数据库提交后的提示，不是事实来源。`docs/project-plan.md` 和 `tests/test_process_integration.py` 都明确依赖“数据库期望状态 + HTTP 周期同步”在 Socket.IO 丢失或 Control Plane 重启后恢复。

## Worker 与 Runner 边界

- `worker/client.py` 统一拥有 Control Plane HTTP path、`X-Worker-Token` 和 `raise_for_status()`；Agent 不应散落裸 `httpx` 请求。
- `LiveAgent` 用 Socket.IO 唤醒，但每次仍从 `/desired-state` 拉取持久化状态；`sync_once()` 执行幂等收敛。
- Worker 持有子进程、signal、凭据文件和工作目录；Control Plane 只保存期望/实际状态和 PID 等元数据。
- Backtest Worker 先校验 bundle SHA-256，再通过 `python -m infinex.runner backtest` 隔离执行。
- `infinex.runner` 是未来接入真实 NautilusTrader 的替换边界。不要把交易引擎实现塞进 `api.py` 或 Worker 协议 client。

## CLI 与配置

`cli.py` 只做参数解析和对象装配，并在命令函数中延迟 import 具体服务，避免导入 CLI 时启动 Control Plane 或 Worker。新增运行参数优先进入 `Settings` 或 Typer option，并保持 `.env.example`、README 命令和进程测试一致。

## 命名与放置规则

- Python module/file 使用 `snake_case`，class/SQLModel 使用 `PascalCase`，函数与局部变量使用 `snake_case`。
- 数据库状态值使用小写字符串，由 `StrEnum` 提供唯一拼写，例如 `BacktestStatus.SUCCEEDED.value`。
- 由 Control Plane 生成的领域 ID 通过 `new_id(prefix)` 创建带前缀的值；`Worker.id` 是注册方提供的稳定标识，不走该 helper。不要在 route 中另写 UUID 格式。
- 时间通过 `utc_now()` 生成 UTC-aware `datetime`；不要混入本地时区或裸 `datetime.now()`。
- API 测试留在 `tests/`；只在纯函数边界测试不足时使用真实进程或 PostgreSQL。

## 禁止模式

- 不要让 Socket.IO payload 成为唯一命令来源；通知可能丢失。
- 不要在 route 中直接管理 Runner 子进程；进程生命周期属于 Worker。
- 不要在 Worker 中重新实现领域状态转换；通过 Control Plane API 上报结果。
- 不要提前实现规划文档中尚未落地的 NATS、多租户或真实交易引擎抽象，并把它写成当前惯例。
