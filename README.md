# Infinex MVP

Infinex is a NautilusTrader-oriented trading control plane MVP. The first implementation focuses on the platform loop: strategy draft, immutable strategy version, artifact bundle, backtest run, worker heartbeat, deployment desired state, and runner lifecycle.

The current runner is a deterministic mock runner. The NautilusTrader runner should replace the `infinex.runner` boundary after the control plane protocol is stable.

## Implemented

- FastAPI control plane with SQLite/PostgreSQL support and OpenAPI docs.
- Strategy draft, immutable candidate version, publish flow, config validation, and SHA-256 bundle artifacts.
- Backtest queue, worker claim/lease, isolated deterministic mock runner, and reproducible metrics.
- Live worker desired-state reconciliation with HTTP polling and Socket.IO wake-up notifications.
- Deployment start/stop commands, independent runner subprocesses, run history, and audit events.
- React, Ant Design, and ECharts console for overview, workers, strategies, backtests, deployments, and audit state.

Workers use the enrollment token only on first registration. The control plane then issues a distinct credential which the Agent stores in its private work directory.

## Requirements

- Python 3.13 managed by `uv`
- Bun for the web console

## Backend

```bash
uv sync --extra dev
uv run infinex init-db
uv run infinex serve
```

`init-db` applies Alembic migrations. The default database is SQLite at `data/infinex.db`; set `DATABASE_URL` to use PostgreSQL.
API documentation is available at `http://127.0.0.1:8002/docs`.

## Worker

Run a one-shot local backtest worker:

```bash
uv run infinex backtest-worker --once
```

Run a live worker agent loop:

```bash
uv run infinex live-agent --worker-id live-local
```

Both workers read `WORKER_ENROLLMENT_TOKEN` on first registration; the development default is `development-enrollment-token`.
Worker commands also accept `WORKER_ID` and `CONTROL_PLANE_URL`; the Compose files use these environment variables to keep their command overrides minimal.

## Web

```bash
cd web
bun install
bun run dev
```

The Vite development server proxies `/api` and `/socket.io` to `http://127.0.0.1:8002`. Set `VITE_API_BASE_URL` when the API runs elsewhere.
For production, run `bun run build` before starting the control plane. FastAPI serves `web/dist` automatically.

## 容器运行

默认的 `docker-compose.yml` 在同一台机器上启动 Control Plane 与 backtest worker。Compose 中的容器显式以 root 用户运行，`data/` 下的 bind mount 目录不存在时由 Docker 自动创建。使用镜像内置的 SQLite 和开发 enrollment token 时可以直接启动：

```bash
docker compose up -d --build
```

生产部署时将 Control Plane 模板复制为标准 `.env` 并至少替换 enrollment token；Docker Compose 会自动读取该文件，不需要额外参数：

```bash
cp .env.control-plane.example .env
# 编辑 .env，至少替换 WORKER_ENROLLMENT_TOKEN
docker compose up -d --build
```

`INFINEX_PORT` 同时控制容器监听端口、宿主机映射端口、healthcheck 和 backtest worker 的内网地址，默认值为 `8002`。例如设置 `INFINEX_PORT=9000` 后，Web Console 位于 `http://127.0.0.1:9000`，API 与文档分别位于 `/api` 和 `/docs`。未提供 `.env` 时，镜像默认使用 `data/control-plane/infinex.db`；连接外部 PostgreSQL 时，在 `.env` 中填写完整 URL：

```dotenv
DATABASE_URL=postgresql+psycopg://user:password@database.example.com/infinex
```

```bash
docker compose up -d --build
```

`data/control-plane` 保存 SQLite 与策略产物，`data/backtest-worker` 保存 backtest worker 的凭据和工作目录；迁移时停止容器并复制整个 `data/` 目录。

Live worker 使用独立的 `docker-compose.live-worker.yml` 部署到交易机器，不依赖本机 Docker 网络中的 Control Plane。在 live worker 机器上同样将对应模板复制为标准 `.env`，然后填写该机器可访问的 HTTPS/私网地址（包含非默认端口时的端口号）、稳定唯一的 `WORKER_ID` 和 enrollment token：

```bash
cp .env.live-worker.example .env
# 编辑 .env 中的 CONTROL_PLANE_URL、WORKER_ID 和 enrollment token
docker compose -f docker-compose.live-worker.yml up -d
```

Live worker 同样由 Compose 以 root 用户运行，其持久凭据位于 `data/live-worker`。迁移该 worker 时应连同此目录一起复制，避免迁移后重新 enrollment。在本地开发之外使用任一 Compose 文件前，Control Plane 与 worker 必须配置相同的初始 `WORKER_ENROLLMENT_TOKEN`。实际部署使用的 `.env` 已被 Git 忽略，不要提交真实 token。

正式版本发布到 GHCR：

```bash
docker pull ghcr.io/imbingox/infinex:latest
```

普通 PR 与 `main` push 只运行 CI。发布正式版本时，手动运行 `Prepare Release` GitHub Action，review 并 squash merge 自动生成的 release PR；随后 `main` CI 会触发 `Publish Release` workflow。

## Tests

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
cd web
bun run typecheck
bun test
bun run build
```

Set `TEST_POSTGRES_URL` to run the PostgreSQL migration and round-trip test. CI provisions PostgreSQL automatically.
