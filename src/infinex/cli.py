from pathlib import Path
from typing import Annotated

import typer

from infinex.control_plane.settings import get_settings

app = typer.Typer(no_args_is_help=True, help="Infinex control plane and worker commands.")


@app.command("init-db")
def init_database() -> None:
    from infinex.control_plane.db import init_db

    init_db()
    typer.echo("Database initialized.")


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind host.")] = "0.0.0.0",
    port: Annotated[int, typer.Option(help="Bind port.")] = 8002,
    reload: Annotated[bool, typer.Option(help="Enable development reload.")] = False,
) -> None:
    import uvicorn

    from infinex.control_plane.logging import configure_logging

    configure_logging()
    uvicorn.run(
        "infinex.control_plane.app:app",
        host=host,
        port=port,
        reload=reload,
        log_config=None,
    )


@app.command("live-agent")
def live_agent(
    worker_id: Annotated[
        str,
        typer.Option(envvar="WORKER_ID", help="Stable worker identifier."),
    ] = "live-local",
    control_plane_url: Annotated[
        str,
        typer.Option(envvar="CONTROL_PLANE_URL"),
    ] = "http://127.0.0.1:8002",
    runtime_version: Annotated[str, typer.Option()] = "py313-nautilus-mock",
    capacity: Annotated[int, typer.Option(min=1)] = 2,
    token: Annotated[str | None, typer.Option(envvar="WORKER_ENROLLMENT_TOKEN")] = None,
    work_dir: Annotated[Path | None, typer.Option()] = None,
    once: Annotated[
        bool,
        typer.Option(help="Perform one reconciliation pass and exit."),
    ] = False,
) -> None:
    from infinex.worker.agent import LiveAgent

    settings = get_settings()
    agent = LiveAgent(
        worker_id=worker_id,
        control_plane_url=control_plane_url,
        runtime_version=runtime_version,
        capacity=capacity,
        token=token or settings.worker_enrollment_token,
        work_dir=work_dir or settings.worker_data_dir / worker_id,
        heartbeat_interval=settings.worker_heartbeat_interval_seconds,
        poll_interval=settings.worker_poll_interval_seconds,
    )
    agent.run(once=once)


@app.command("backtest-worker")
def backtest_worker(
    worker_id: Annotated[
        str,
        typer.Option(envvar="WORKER_ID", help="Stable worker identifier."),
    ] = "backtest-local",
    control_plane_url: Annotated[
        str,
        typer.Option(envvar="CONTROL_PLANE_URL"),
    ] = "http://127.0.0.1:8002",
    runtime_version: Annotated[str, typer.Option()] = "py313-nautilus-mock",
    token: Annotated[str | None, typer.Option(envvar="WORKER_ENROLLMENT_TOKEN")] = None,
    work_dir: Annotated[Path | None, typer.Option()] = None,
    once: Annotated[bool, typer.Option(help="Claim at most one job and exit.")] = False,
) -> None:
    from infinex.worker.backtest import BacktestWorker

    settings = get_settings()
    worker = BacktestWorker(
        worker_id=worker_id,
        control_plane_url=control_plane_url,
        runtime_version=runtime_version,
        token=token or settings.worker_enrollment_token,
        work_dir=work_dir or settings.worker_data_dir / worker_id,
        poll_interval=settings.worker_poll_interval_seconds,
    )
    worker.run(once=once)


if __name__ == "__main__":
    app()
