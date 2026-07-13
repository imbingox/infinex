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

## Web

```bash
cd web
bun install
bun run dev
```

The Vite development server proxies `/api` and `/socket.io` to `http://127.0.0.1:8002`. Set `VITE_API_BASE_URL` when the API runs elsewhere.
For production, run `bun run build` before starting the control plane. FastAPI serves `web/dist` automatically.

## 容器运行

默认的 `docker-compose.yml` 在同一台机器上启动 Control Plane 与 backtest worker。先创建宿主机数据目录，并将目录交给镜像中的非 root 用户（UID/GID `10001`）：

```bash
cp .env.control-plane.example .env.control-plane
# 编辑 .env.control-plane，至少替换 WORKER_ENROLLMENT_TOKEN
mkdir -p data/control-plane data/backtest-worker
sudo chown -R 10001:10001 data/control-plane data/backtest-worker
docker compose --env-file .env.control-plane up -d --build
```

Web Console 与 API 位于 `http://127.0.0.1:8002`。未设置 `DATABASE_URL`（或值为空）时，Compose 使用 `data/control-plane/infinex.db`；连接外部 PostgreSQL 时，在 `.env.control-plane` 中填写完整 URL：

```dotenv
DATABASE_URL=postgresql+psycopg://user:password@database.example.com/infinex
```

```bash
docker compose --env-file .env.control-plane up -d --build
```

`data/control-plane` 保存 SQLite 与策略产物，`data/backtest-worker` 保存 backtest worker 的凭据和工作目录。可以通过 `INFINEX_DATA_ROOT=/srv/infinex` 将两者统一放到其他宿主机目录；迁移时停止容器并复制整个数据根目录，同时保留 UID/GID `10001` 的写权限。

Live worker 使用独立的 `docker-compose.live-worker.yml` 部署到交易机器，不依赖本机 Docker 网络中的 Control Plane。其 URL 必须是该机器能够访问的 HTTPS 或私网地址，`LIVE_WORKER_ID` 必须保持稳定且唯一：

```bash
cp .env.live-worker.example .env.live-worker
# 编辑 .env.live-worker 中的 URL、worker ID 和 enrollment token
mkdir -p data/live-worker
sudo chown -R 10001:10001 data/live-worker
docker compose \
  --env-file .env.live-worker \
  -f docker-compose.live-worker.yml \
  up -d
```

Live worker 的持久凭据位于 `data/live-worker`。迁移该 worker 时应连同此目录一起复制，避免迁移后重新 enrollment。在本地开发之外使用任一 Compose 文件前，Control Plane 与 worker 必须配置相同的初始 `WORKER_ENROLLMENT_TOKEN`。`.env.control-plane` 与 `.env.live-worker` 均已被 Git 忽略，不要提交真实 token。

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
