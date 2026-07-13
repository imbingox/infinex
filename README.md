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

构建并启动 PostgreSQL 与 Control Plane：

```bash
docker compose up --build
```

Web Console 与 API 位于 `http://127.0.0.1:8002`。Compose 使用 named volume 保存 PostgreSQL 与 Infinex 数据；在本地开发之外使用该示例前，必须显式设置 `POSTGRES_PASSWORD` 与 `WORKER_ENROLLMENT_TOKEN`。

使用同一镜像启动可选的 backtest/live workers：

```bash
docker compose --profile workers up --build
```

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
