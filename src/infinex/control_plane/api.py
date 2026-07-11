import secrets
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from infinex.control_plane.db import get_session
from infinex.control_plane.models import (
    AuditEvent,
    BacktestRun,
    BacktestStatus,
    Command,
    CommandStatus,
    ConfigVersion,
    Deployment,
    DeploymentState,
    Run,
    Strategy,
    StrategyDraft,
    StrategyVersion,
    StrategyVersionStatus,
    Worker,
    WorkerRole,
    utc_now,
)
from infinex.control_plane.realtime import publish_update
from infinex.control_plane.schemas import (
    AgentRunStarted,
    AgentRunStopped,
    BacktestCreate,
    BacktestLeaseRenew,
    BacktestResultReport,
    CommandAck,
    ConfigVersionCreate,
    DeploymentCreate,
    StrategyCreate,
    StrategyDraftUpdate,
    StrategyVersionCreate,
    WorkerHeartbeat,
    WorkerRegister,
)
from infinex.control_plane.security import (
    generate_worker_token,
    hash_worker_token,
    verify_worker_token,
)
from infinex.control_plane.services import (
    acknowledge_command,
    assert_worker_compatible,
    audit,
    claim_next_backtest,
    create_candidate_version,
    create_config_version,
    create_deployment_command,
    get_or_404,
    heartbeat_worker,
    latest_draft,
    publish_version,
    refresh_worker_status,
    start_run_for_deployment,
    stop_run_for_deployment,
    touch_worker,
    upsert_draft,
)
from infinex.control_plane.settings import get_settings

router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]


WorkerToken = Annotated[str | None, Header()]


def require_worker_identity(
    session: Session,
    worker_id: str,
    token: str | None,
) -> Worker:
    worker = get_or_404(session, Worker, worker_id)
    if not token or not verify_worker_token(token, worker.credential_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid worker credential",
        )
    return worker


def commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Database constraint conflict") from exc


def worker_view(worker: Worker) -> dict[str, Any]:
    return {
        "id": worker.id,
        "role": worker.role,
        "runtime_version": worker.runtime_version,
        "status": worker.status,
        "capacity": worker.capacity,
        "current_runs": worker.current_runs,
        "last_heartbeat_at": worker.last_heartbeat_at,
        "metadata": worker.metadata_json,
        "created_at": worker.created_at,
    }


def assert_worker_owns(worker_id: str, object_worker_id: str) -> None:
    if worker_id != object_worker_id:
        raise HTTPException(status_code=403, detail="Object belongs to another worker")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/summary")
def summary(session: SessionDep) -> dict[str, Any]:
    workers = session.exec(select(Worker)).all()
    settings = get_settings()
    changed = False
    for worker in workers:
        previous = worker.status
        refresh_worker_status(worker, settings.worker_offline_after_seconds)
        changed = changed or previous != worker.status
    if changed:
        commit(session)

    backtests = session.exec(select(BacktestRun)).all()
    deployments = session.exec(select(Deployment)).all()
    strategies = session.exec(select(Strategy)).all()
    return {
        "workers": {
            "total": len(workers),
            "online": sum(worker.status == "online" for worker in workers),
            "degraded": sum(worker.status == "degraded" for worker in workers),
            "offline": sum(worker.status == "offline" for worker in workers),
        },
        "strategies": {"total": len(strategies)},
        "backtests": {
            "total": len(backtests),
            "active": sum(
                run.status
                in {
                    BacktestStatus.QUEUED.value,
                    BacktestStatus.CLAIMED.value,
                    BacktestStatus.RUNNING.value,
                }
                for run in backtests
            ),
            "succeeded": sum(run.status == BacktestStatus.SUCCEEDED.value for run in backtests),
            "failed": sum(run.status == BacktestStatus.FAILED.value for run in backtests),
        },
        "deployments": {
            "total": len(deployments),
            "running": sum(
                item.actual_state == DeploymentState.RUNNING.value for item in deployments
            ),
            "failed": sum(
                item.actual_state == DeploymentState.FAILED.value for item in deployments
            ),
        },
    }


@router.post("/workers/register", status_code=status.HTTP_201_CREATED)
async def register_worker(
    payload: WorkerRegister,
    session: SessionDep,
    x_worker_token: WorkerToken = None,
) -> dict[str, Any]:
    settings = get_settings()
    existing = session.get(Worker, payload.worker_id)
    issued_token: str | None = None
    credential_hash: str | None = None
    if existing is None:
        if not x_worker_token or not secrets.compare_digest(
            x_worker_token,
            settings.worker_enrollment_token,
        ):
            raise HTTPException(status_code=401, detail="Invalid worker enrollment token")
        issued_token = generate_worker_token()
        credential_hash = hash_worker_token(issued_token)
    elif x_worker_token and verify_worker_token(x_worker_token, existing.credential_hash):
        pass
    elif x_worker_token and secrets.compare_digest(
        x_worker_token,
        settings.worker_enrollment_token,
    ):
        issued_token = generate_worker_token()
        credential_hash = hash_worker_token(issued_token)
    else:
        raise HTTPException(status_code=401, detail="Invalid worker credential")

    worker = touch_worker(
        session,
        payload.worker_id,
        payload.role,
        payload.runtime_version,
        payload.capacity,
        payload.metadata,
        credential_hash,
    )
    commit(session)
    session.refresh(worker)
    await publish_update("worker", "registered", worker.id)
    response = worker_view(worker)
    if issued_token:
        response["worker_token"] = issued_token
    return response


@router.post("/workers/{worker_id}/heartbeat")
async def worker_heartbeat(
    worker_id: str,
    payload: WorkerHeartbeat,
    session: SessionDep,
    x_worker_token: WorkerToken = None,
) -> dict[str, Any]:
    worker = require_worker_identity(session, worker_id, x_worker_token)
    heartbeat_worker(
        worker,
        payload.runtime_version,
        payload.capacity,
        payload.current_runs,
        payload.metadata,
    )
    commit(session)
    session.refresh(worker)
    await publish_update("worker", "heartbeat", worker.id)
    return worker_view(worker)


@router.get("/workers")
def list_workers(session: SessionDep) -> list[dict[str, Any]]:
    workers = session.exec(select(Worker).order_by(Worker.id)).all()
    settings = get_settings()
    changed = False
    for worker in workers:
        previous = worker.status
        refresh_worker_status(worker, settings.worker_offline_after_seconds)
        changed = changed or previous != worker.status
    if changed:
        commit(session)
    return [worker_view(worker) for worker in workers]


@router.get("/workers/{worker_id}")
def get_worker(worker_id: str, session: SessionDep) -> dict[str, Any]:
    worker = get_or_404(session, Worker, worker_id)
    refresh_worker_status(worker, get_settings().worker_offline_after_seconds)
    commit(session)
    return worker_view(worker)


@router.get("/workers/{worker_id}/desired-state")
def worker_desired_state(
    worker_id: str,
    session: SessionDep,
    x_worker_token: WorkerToken = None,
) -> dict[str, Any]:
    require_worker_identity(session, worker_id, x_worker_token)
    deployments = session.exec(
        select(Deployment).where(Deployment.worker_id == worker_id).order_by(Deployment.created_at)
    ).all()
    commands = session.exec(
        select(Command)
        .where(
            Command.worker_id == worker_id,
            Command.status.in_([CommandStatus.PENDING.value, CommandStatus.ACKED.value]),
        )
        .order_by(Command.created_at)
    ).all()
    return {"deployments": deployments, "commands": commands}


@router.post("/commands/{command_id}/ack")
async def ack_command(
    command_id: str,
    payload: CommandAck,
    session: SessionDep,
    x_worker_token: WorkerToken = None,
) -> Command:
    require_worker_identity(session, payload.worker_id, x_worker_token)
    command = get_or_404(session, Command, command_id)
    acknowledge_command(session, command, payload.worker_id)
    commit(session)
    session.refresh(command)
    await publish_update("command", "acknowledged", command.id)
    return command


@router.get("/commands")
def list_commands(
    session: SessionDep,
    worker_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Command]:
    statement = select(Command)
    if worker_id:
        statement = statement.where(Command.worker_id == worker_id)
    return session.exec(statement.order_by(Command.created_at.desc()).limit(limit)).all()


@router.post("/strategies", status_code=status.HTTP_201_CREATED)
async def create_strategy(payload: StrategyCreate, session: SessionDep) -> Strategy:
    strategy = Strategy(name=payload.name, description=payload.description, owner=payload.owner)
    session.add(strategy)
    session.flush()
    audit(session, "strategy_created", "strategy", strategy.id, after={"name": strategy.name})
    commit(session)
    session.refresh(strategy)
    await publish_update("strategy", "created", strategy.id)
    return strategy


@router.get("/strategies")
def list_strategies(session: SessionDep) -> list[Strategy]:
    return session.exec(select(Strategy).order_by(Strategy.created_at.desc())).all()


@router.get("/strategies/{strategy_id}")
def get_strategy(strategy_id: str, session: SessionDep) -> dict[str, Any]:
    strategy = get_or_404(session, Strategy, strategy_id)
    draft = latest_draft(session, strategy_id)
    versions = session.exec(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.created_at.desc())
    ).all()
    return {"strategy": strategy, "draft": draft, "versions": versions}


@router.put("/strategies/{strategy_id}/draft")
async def save_strategy_draft(
    strategy_id: str,
    payload: StrategyDraftUpdate,
    session: SessionDep,
) -> StrategyDraft:
    strategy = get_or_404(session, Strategy, strategy_id)
    draft = upsert_draft(session, strategy, payload)
    commit(session)
    session.refresh(draft)
    await publish_update("strategy_draft", "saved", draft.id)
    return draft


@router.post("/strategies/{strategy_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_strategy_version(
    strategy_id: str,
    payload: StrategyVersionCreate,
    session: SessionDep,
) -> StrategyVersion:
    strategy = get_or_404(session, Strategy, strategy_id)
    draft = latest_draft(session, strategy_id)
    if draft is None:
        raise HTTPException(status_code=409, detail="Strategy draft is required")
    version = create_candidate_version(session, strategy, draft, payload.source_ref or None)
    commit(session)
    session.refresh(version)
    await publish_update("strategy_version", "created", version.id)
    return version


@router.get("/strategy-versions")
def list_strategy_versions(
    session: SessionDep,
    strategy_id: str | None = None,
) -> list[StrategyVersion]:
    statement = select(StrategyVersion)
    if strategy_id:
        statement = statement.where(StrategyVersion.strategy_id == strategy_id)
    return session.exec(statement.order_by(StrategyVersion.created_at.desc())).all()


@router.get("/strategy-versions/{version_id}")
def get_strategy_version(version_id: str, session: SessionDep) -> StrategyVersion:
    return get_or_404(session, StrategyVersion, version_id)


@router.post("/strategy-versions/{version_id}/publish")
async def publish_strategy_version(version_id: str, session: SessionDep) -> StrategyVersion:
    version = get_or_404(session, StrategyVersion, version_id)
    publish_version(session, version)
    commit(session)
    session.refresh(version)
    await publish_update("strategy_version", "published", version.id)
    return version


@router.get("/strategy-versions/{version_id}/artifact")
def download_strategy_artifact(version_id: str, session: SessionDep) -> FileResponse:
    version = get_or_404(session, StrategyVersion, version_id)
    if not version.artifact_path:
        raise HTTPException(status_code=404, detail="Strategy artifact not found")
    artifact_path = Path(version.artifact_path)
    if not artifact_path.is_file():
        raise HTTPException(status_code=404, detail="Strategy artifact file not found")
    headers = {"ETag": f'"{version.artifact_sha256}"'} if version.artifact_sha256 else None
    return FileResponse(
        artifact_path,
        filename=f"{version.version_label}.zip",
        media_type="application/zip",
        headers=headers,
    )


@router.post(
    "/strategy-versions/{version_id}/configs",
    status_code=status.HTTP_201_CREATED,
)
async def add_config_version(
    version_id: str,
    payload: ConfigVersionCreate,
    session: SessionDep,
) -> ConfigVersion:
    version = get_or_404(session, StrategyVersion, version_id)
    config = create_config_version(session, version, payload.config, payload.source)
    session.flush()
    commit(session)
    session.refresh(config)
    await publish_update("config_version", "created", config.id)
    return config


@router.get("/config-versions")
def list_config_versions(
    session: SessionDep,
    strategy_version_id: str | None = None,
) -> list[ConfigVersion]:
    statement = select(ConfigVersion)
    if strategy_version_id:
        statement = statement.where(ConfigVersion.strategy_version_id == strategy_version_id)
    return session.exec(statement.order_by(ConfigVersion.created_at.desc())).all()


@router.post("/backtests", status_code=status.HTTP_201_CREATED)
async def create_backtest(payload: BacktestCreate, session: SessionDep) -> BacktestRun:
    get_or_404(session, StrategyVersion, payload.strategy_version_id)
    config = get_or_404(session, ConfigVersion, payload.config_version_id)
    if config.strategy_version_id != payload.strategy_version_id:
        raise HTTPException(
            status_code=409, detail="ConfigVersion belongs to another StrategyVersion"
        )
    run = BacktestRun(
        strategy_version_id=payload.strategy_version_id,
        config_version_id=payload.config_version_id,
        dataset=payload.dataset,
        start_time=payload.start_time,
        end_time=payload.end_time,
    )
    session.add(run)
    session.flush()
    audit(session, "backtest_created", "backtest_run", run.id)
    commit(session)
    session.refresh(run)
    await publish_update("backtest_run", "created", run.id)
    return run


@router.get("/backtests")
def list_backtests(
    session: SessionDep,
    run_status: str | None = Query(default=None, alias="status"),
) -> list[BacktestRun]:
    statement = select(BacktestRun)
    if run_status:
        statement = statement.where(BacktestRun.status == run_status)
    return session.exec(statement.order_by(BacktestRun.created_at.desc())).all()


@router.get("/backtests/{run_id}")
def get_backtest(run_id: str, session: SessionDep) -> BacktestRun:
    return get_or_404(session, BacktestRun, run_id)


@router.post("/workers/{worker_id}/backtests/claim")
async def claim_backtest(
    worker_id: str,
    session: SessionDep,
    x_worker_token: WorkerToken = None,
) -> Any:
    worker = require_worker_identity(session, worker_id, x_worker_token)
    if worker.role != WorkerRole.BACKTEST.value:
        raise HTTPException(status_code=409, detail="Worker is not a backtest worker")
    run = claim_next_backtest(session, worker)
    if run is None:
        commit(session)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    version = get_or_404(session, StrategyVersion, run.strategy_version_id)
    config = get_or_404(session, ConfigVersion, run.config_version_id)
    commit(session)
    session.refresh(run)
    await publish_update("backtest_run", "claimed", run.id)
    return {
        "run": run,
        "strategy_version": version,
        "config_version": config,
        "artifact_url": f"/api/strategy-versions/{version.id}/artifact",
    }


@router.post("/backtests/{run_id}/running")
async def mark_backtest_running(
    run_id: str,
    payload: BacktestLeaseRenew,
    session: SessionDep,
    x_worker_token: WorkerToken = None,
) -> BacktestRun:
    require_worker_identity(session, payload.worker_id, x_worker_token)
    run = get_or_404(session, BacktestRun, run_id)
    assert_worker_owns(payload.worker_id, run.worker_id or "")
    run.status = BacktestStatus.RUNNING.value
    run.lease_expires_at = utc_now() + timedelta(seconds=payload.lease_seconds)
    run.updated_at = utc_now()
    commit(session)
    session.refresh(run)
    await publish_update("backtest_run", "running", run.id)
    return run


@router.post("/backtests/{run_id}/lease")
def renew_backtest_lease(
    run_id: str,
    payload: BacktestLeaseRenew,
    session: SessionDep,
    x_worker_token: WorkerToken = None,
) -> BacktestRun:
    require_worker_identity(session, payload.worker_id, x_worker_token)
    run = get_or_404(session, BacktestRun, run_id)
    assert_worker_owns(payload.worker_id, run.worker_id or "")
    if run.status not in {BacktestStatus.CLAIMED.value, BacktestStatus.RUNNING.value}:
        raise HTTPException(status_code=409, detail="Backtest is not active")
    run.lease_expires_at = utc_now() + timedelta(seconds=payload.lease_seconds)
    run.updated_at = utc_now()
    commit(session)
    session.refresh(run)
    return run


@router.post("/backtests/{run_id}/complete")
async def complete_backtest(
    run_id: str,
    payload: BacktestResultReport,
    session: SessionDep,
    x_worker_token: WorkerToken = None,
) -> BacktestRun:
    require_worker_identity(session, payload.worker_id, x_worker_token)
    run = get_or_404(session, BacktestRun, run_id)
    assert_worker_owns(payload.worker_id, run.worker_id or "")
    run.status = BacktestStatus.FAILED.value if payload.error else BacktestStatus.SUCCEEDED.value
    run.result = payload.result
    run.error = payload.error
    run.lease_expires_at = None
    run.updated_at = utc_now()
    audit(
        session,
        "backtest_failed" if payload.error else "backtest_succeeded",
        "backtest_run",
        run.id,
        after={"error": payload.error},
        actor=f"worker:{payload.worker_id}",
    )
    commit(session)
    session.refresh(run)
    await publish_update("backtest_run", "completed", run.id)
    return run


@router.post("/deployments", status_code=status.HTTP_201_CREATED)
async def create_deployment(payload: DeploymentCreate, session: SessionDep) -> Deployment:
    worker = get_or_404(session, Worker, payload.worker_id)
    if worker.role != WorkerRole.LIVE.value:
        raise HTTPException(status_code=409, detail="Deployment requires a live worker")
    version = get_or_404(session, StrategyVersion, payload.strategy_version_id)
    if version.status != StrategyVersionStatus.PUBLISHED.value:
        raise HTTPException(
            status_code=409, detail="Live deployment requires a published strategy version"
        )
    assert_worker_compatible(worker, version)
    config = get_or_404(session, ConfigVersion, payload.config_version_id)
    if config.strategy_version_id != version.id:
        raise HTTPException(
            status_code=409, detail="ConfigVersion belongs to another StrategyVersion"
        )
    deployment = Deployment(**payload.model_dump())
    session.add(deployment)
    session.flush()
    audit(session, "deployment_created", "deployment", deployment.id)
    commit(session)
    session.refresh(deployment)
    await publish_update("deployment", "created", deployment.id, worker_id=deployment.worker_id)
    return deployment


@router.get("/deployments")
def list_deployments(
    session: SessionDep,
    worker_id: str | None = None,
) -> list[Deployment]:
    statement = select(Deployment)
    if worker_id:
        statement = statement.where(Deployment.worker_id == worker_id)
    return session.exec(statement.order_by(Deployment.created_at.desc())).all()


@router.get("/deployments/{deployment_id}")
def get_deployment(deployment_id: str, session: SessionDep) -> Deployment:
    return get_or_404(session, Deployment, deployment_id)


@router.post("/deployments/{deployment_id}/start")
async def start_deployment(deployment_id: str, session: SessionDep) -> dict[str, Any]:
    deployment = get_or_404(session, Deployment, deployment_id)
    if (
        deployment.desired_state == DeploymentState.RUNNING.value
        and deployment.actual_state == DeploymentState.RUNNING.value
    ):
        return {"deployment": deployment, "command": None}
    command = create_deployment_command(
        session,
        deployment,
        "START_DEPLOYMENT",
        DeploymentState.RUNNING,
    )
    session.flush()
    commit(session)
    session.refresh(deployment)
    session.refresh(command)
    await publish_update(
        "deployment", "start_requested", deployment.id, worker_id=deployment.worker_id
    )
    return {"deployment": deployment, "command": command}


@router.post("/deployments/{deployment_id}/stop")
async def stop_deployment(deployment_id: str, session: SessionDep) -> dict[str, Any]:
    deployment = get_or_404(session, Deployment, deployment_id)
    if (
        deployment.desired_state == DeploymentState.STOPPED.value
        and deployment.actual_state == DeploymentState.STOPPED.value
    ):
        return {"deployment": deployment, "command": None}
    command = create_deployment_command(
        session,
        deployment,
        "STOP_DEPLOYMENT",
        DeploymentState.STOPPED,
    )
    session.flush()
    commit(session)
    session.refresh(deployment)
    session.refresh(command)
    await publish_update(
        "deployment", "stop_requested", deployment.id, worker_id=deployment.worker_id
    )
    return {"deployment": deployment, "command": command}


@router.post("/deployments/{deployment_id}/agent/started")
async def agent_run_started(
    deployment_id: str,
    payload: AgentRunStarted,
    session: SessionDep,
    x_worker_token: WorkerToken = None,
) -> Run:
    require_worker_identity(session, payload.worker_id, x_worker_token)
    deployment = get_or_404(session, Deployment, deployment_id)
    assert_worker_owns(payload.worker_id, deployment.worker_id)
    run = start_run_for_deployment(
        session,
        deployment,
        payload.pid,
        actor=f"worker:{payload.worker_id}",
    )
    commit(session)
    session.refresh(run)
    await publish_update("deployment", "running", deployment.id)
    return run


@router.post("/deployments/{deployment_id}/agent/stopped")
async def agent_run_stopped(
    deployment_id: str,
    payload: AgentRunStopped,
    session: SessionDep,
    x_worker_token: WorkerToken = None,
) -> dict[str, Any]:
    require_worker_identity(session, payload.worker_id, x_worker_token)
    deployment = get_or_404(session, Deployment, deployment_id)
    assert_worker_owns(payload.worker_id, deployment.worker_id)
    command = session.get(Command, payload.command_id) if payload.command_id else None
    if command is None:
        command = session.exec(
            select(Command).where(
                Command.target_id == deployment.id,
                Command.desired_revision == deployment.desired_revision,
                Command.status.in_([CommandStatus.PENDING.value, CommandStatus.ACKED.value]),
            )
        ).first()
    run = stop_run_for_deployment(
        session,
        deployment,
        payload.run_id,
        payload.exit_code,
        payload.error,
        command,
        actor=f"worker:{payload.worker_id}",
    )
    commit(session)
    if run:
        session.refresh(run)
    await publish_update("deployment", "stopped", deployment.id)
    return {"deployment": deployment, "run": run}


@router.get("/runs")
def list_runs(
    session: SessionDep,
    deployment_id: str | None = None,
) -> list[Run]:
    statement = select(Run)
    if deployment_id:
        statement = statement.where(Run.deployment_id == deployment_id)
    return session.exec(statement.order_by(Run.created_at.desc())).all()


@router.get("/audit-events")
def list_audit_events(
    session: SessionDep,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditEvent]:
    return session.exec(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    ).all()
