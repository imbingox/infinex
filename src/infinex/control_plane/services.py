from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from sqlmodel import Session, select

from infinex.control_plane.artifacts import (
    build_strategy_bundle,
    config_hash,
    source_snapshot_hash,
)
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
    RunStatus,
    Strategy,
    StrategyDraft,
    StrategyVersion,
    StrategyVersionStatus,
    Worker,
    WorkerStatus,
    new_id,
    utc_now,
)
from infinex.control_plane.schemas import StrategyDraftUpdate


def get_or_404(session: Session, model: type, object_id: str):
    item = session.get(model, object_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found"
        )
    return item


def audit(
    session: Session,
    action: str,
    object_type: str,
    object_id: str,
    before: dict | None = None,
    after: dict | None = None,
    actor: str = "system",
) -> None:
    session.add(
        AuditEvent(
            actor=actor,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before=before or {},
            after=after or {},
        )
    )


def latest_draft(session: Session, strategy_id: str) -> StrategyDraft | None:
    statement = (
        select(StrategyDraft)
        .where(StrategyDraft.strategy_id == strategy_id)
        .order_by(StrategyDraft.updated_at.desc())
    )
    return session.exec(statement).first()


def upsert_draft(
    session: Session,
    strategy: Strategy,
    payload: StrategyDraftUpdate,
) -> StrategyDraft:
    draft = latest_draft(session, strategy.id)
    now = utc_now()
    if draft is None:
        draft = StrategyDraft(
            strategy_id=strategy.id,
            source_code=payload.source_code,
            entrypoint=payload.entrypoint,
            runtime_version=payload.runtime_version,
            config_schema=payload.config_schema,
            defaults=payload.defaults,
            source_ref=payload.source_ref,
            notes=payload.notes,
        )
        session.add(draft)
    else:
        draft.source_code = payload.source_code
        draft.entrypoint = payload.entrypoint
        draft.runtime_version = payload.runtime_version
        draft.config_schema = payload.config_schema
        draft.defaults = payload.defaults
        draft.source_ref = payload.source_ref
        draft.notes = payload.notes
        draft.updated_at = now
    strategy.updated_at = now
    audit(session, "strategy_draft_saved", "strategy", strategy.id, after={"draft_id": draft.id})
    return draft


def create_candidate_version(
    session: Session,
    strategy: Strategy,
    draft: StrategyDraft,
    source_ref: dict | None = None,
) -> StrategyVersion:
    snapshot_sha = source_snapshot_hash(
        draft.source_code,
        draft.entrypoint,
        draft.runtime_version,
        draft.config_schema,
        draft.defaults,
    )
    now_label = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    version = StrategyVersion(
        strategy_id=strategy.id,
        version_label=f"candidate-{now_label}",
        status=StrategyVersionStatus.CANDIDATE.value,
        source_snapshot_sha256=snapshot_sha,
        entrypoint=draft.entrypoint,
        runtime_version=draft.runtime_version,
        config_schema=draft.config_schema,
        defaults=draft.defaults,
        source_ref=source_ref if source_ref is not None else draft.source_ref,
    )
    session.add(version)
    session.flush()

    artifact_path, artifact_sha = build_strategy_bundle(version, draft.source_code)
    version.artifact_path = str(artifact_path)
    version.artifact_sha256 = artifact_sha

    default_config = ConfigVersion(
        strategy_version_id=version.id,
        config=draft.defaults,
        config_hash=config_hash(draft.defaults),
        source="defaults",
    )
    session.add(default_config)
    audit(
        session,
        "strategy_version_created",
        "strategy_version",
        version.id,
        after={"status": version.status, "artifact_sha256": artifact_sha},
    )
    return version


def publish_version(session: Session, version: StrategyVersion) -> StrategyVersion:
    if version.status == StrategyVersionStatus.ARCHIVED.value:
        raise HTTPException(
            status_code=409, detail="Archived strategy versions cannot be published"
        )
    version.status = StrategyVersionStatus.PUBLISHED.value
    version.published_at = utc_now()
    audit(session, "strategy_version_published", "strategy_version", version.id)
    return version


def validate_config(schema: dict, config: dict) -> None:
    if not schema:
        return
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(config)
    except SchemaError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid config schema: {exc.message}"
        ) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid config: {exc.message}") from exc


def create_config_version(
    session: Session,
    version: StrategyVersion,
    config: dict,
    source: str,
) -> ConfigVersion:
    validate_config(version.config_schema, config)
    config_version = ConfigVersion(
        strategy_version_id=version.id,
        config=config,
        config_hash=config_hash(config),
        source=source,
    )
    session.add(config_version)
    audit(
        session,
        "config_version_created",
        "config_version",
        config_version.id,
        after={"strategy_version_id": version.id, "config_hash": config_version.config_hash},
    )
    return config_version


def assert_worker_compatible(worker: Worker, version: StrategyVersion) -> None:
    if worker.runtime_version != version.runtime_version:
        detail = (
            f"Worker runtime {worker.runtime_version} != strategy runtime {version.runtime_version}"
        )
        raise HTTPException(
            status_code=409,
            detail=detail,
        )


def claim_next_backtest(
    session: Session, worker: Worker, lease_seconds: int = 300
) -> BacktestRun | None:
    now = utc_now()
    expired_statement = select(BacktestRun).where(
        BacktestRun.status.in_([BacktestStatus.CLAIMED.value, BacktestStatus.RUNNING.value]),
        BacktestRun.lease_expires_at.is_not(None),
        BacktestRun.lease_expires_at < now,
    )
    for expired in session.exec(expired_statement).all():
        expired.status = BacktestStatus.QUEUED.value
        expired.worker_id = None
        expired.lease_expires_at = None
        expired.updated_at = now
        audit(session, "backtest_lease_expired", "backtest_run", expired.id)

    statement = (
        select(BacktestRun)
        .where(BacktestRun.status == BacktestStatus.QUEUED.value)
        .order_by(BacktestRun.created_at)
        .with_for_update(skip_locked=True)
    )
    run = session.exec(statement).first()
    if run is None:
        return None
    version = get_or_404(session, StrategyVersion, run.strategy_version_id)
    assert_worker_compatible(worker, version)
    run.status = BacktestStatus.CLAIMED.value
    run.worker_id = worker.id
    run.lease_expires_at = now + timedelta(seconds=lease_seconds)
    run.updated_at = now
    audit(
        session,
        "backtest_claimed",
        "backtest_run",
        run.id,
        after={"worker_id": worker.id},
        actor=f"worker:{worker.id}",
    )
    return run


def touch_worker(
    session: Session,
    worker_id: str,
    role: str,
    runtime_version: str,
    capacity: int,
    metadata: dict,
    credential_hash: str | None = None,
) -> Worker:
    worker = session.get(Worker, worker_id)
    if worker is None:
        worker = Worker(
            id=worker_id,
            role=role,
            runtime_version=runtime_version,
            credential_hash=credential_hash,
            capacity=capacity,
            metadata_json=metadata,
        )
        session.add(worker)
        audit(
            session,
            "worker_registered",
            "worker",
            worker_id,
            after={"role": role},
            actor=f"worker:{worker_id}",
        )
    else:
        worker.role = role
        worker.runtime_version = runtime_version
        worker.capacity = capacity
        worker.metadata_json = metadata
        if credential_hash is not None:
            worker.credential_hash = credential_hash
        worker.status = WorkerStatus.ONLINE.value
        worker.last_heartbeat_at = utc_now()
    return worker


def heartbeat_worker(
    worker: Worker,
    runtime_version: str | None,
    capacity: int | None,
    current_runs: int | None,
    metadata: dict | None,
) -> Worker:
    if runtime_version is not None:
        worker.runtime_version = runtime_version
    if capacity is not None:
        worker.capacity = capacity
    if current_runs is not None:
        worker.current_runs = current_runs
    if metadata is not None:
        worker.metadata_json = metadata
    worker.status = WorkerStatus.ONLINE.value
    worker.last_heartbeat_at = utc_now()
    return worker


def refresh_worker_status(worker: Worker, offline_after_seconds: int) -> Worker:
    last_heartbeat = worker.last_heartbeat_at
    if last_heartbeat.tzinfo is None:
        last_heartbeat = last_heartbeat.replace(tzinfo=UTC)
    age = utc_now() - last_heartbeat
    if age.total_seconds() >= offline_after_seconds:
        worker.status = WorkerStatus.OFFLINE.value
    elif age.total_seconds() >= offline_after_seconds / 2:
        worker.status = WorkerStatus.DEGRADED.value
    else:
        worker.status = WorkerStatus.ONLINE.value
    return worker


def sweep_worker_statuses(session: Session, offline_after_seconds: int) -> list[Worker]:
    changed: list[Worker] = []
    for worker in session.exec(select(Worker)).all():
        previous = worker.status
        refresh_worker_status(worker, offline_after_seconds)
        if worker.status != previous:
            changed.append(worker)
            audit(
                session,
                "worker_status_changed",
                "worker",
                worker.id,
                before={"status": previous},
                after={"status": worker.status},
            )
    return changed


def acknowledge_command(session: Session, command: Command, worker_id: str) -> Command:
    if command.worker_id != worker_id:
        raise HTTPException(status_code=403, detail="Command belongs to another worker")
    if command.status == CommandStatus.PENDING.value:
        command.status = CommandStatus.ACKED.value
        audit(
            session,
            "command_acknowledged",
            "command",
            command.id,
            after={"worker_id": worker_id},
            actor=f"worker:{worker_id}",
        )
    return command


def complete_command(
    session: Session,
    command: Command | None,
    *,
    result: dict | None = None,
    error: str | None = None,
    actor: str = "system",
) -> None:
    if command is None:
        return
    command.status = CommandStatus.FAILED.value if error else CommandStatus.SUCCEEDED.value
    command.result = result or ({"error": error} if error else {})
    command.completed_at = utc_now()
    audit(
        session,
        "command_failed" if error else "command_succeeded",
        "command",
        command.id,
        after=command.result,
        actor=actor,
    )


def create_deployment_command(
    session: Session,
    deployment: Deployment,
    command_type: str,
    desired_state: DeploymentState,
) -> Command:
    before = {
        "desired_state": deployment.desired_state,
        "desired_revision": deployment.desired_revision,
        "generation": deployment.generation,
    }
    deployment.desired_state = desired_state.value
    deployment.desired_revision += 1
    deployment.generation += 1
    deployment.updated_at = utc_now()
    command = Command(
        type=command_type,
        target_type="deployment",
        target_id=deployment.id,
        worker_id=deployment.worker_id,
        desired_revision=deployment.desired_revision,
        payload={
            "deployment_id": deployment.id,
            "strategy_version_id": deployment.strategy_version_id,
            "config_version_id": deployment.config_version_id,
            "generation": deployment.generation,
            "desired_state": deployment.desired_state,
        },
    )
    session.add(command)
    audit(
        session,
        f"deployment_{command_type.lower()}",
        "deployment",
        deployment.id,
        before=before,
        after={
            "desired_state": deployment.desired_state,
            "desired_revision": deployment.desired_revision,
            "generation": deployment.generation,
        },
    )
    return command


def start_run_for_deployment(
    session: Session,
    deployment: Deployment,
    pid: int | None,
    actor: str = "system",
) -> Run:
    statement = select(Run).where(
        Run.deployment_id == deployment.id,
        Run.status.in_(
            [RunStatus.STARTING.value, RunStatus.RUNNING.value, RunStatus.STOPPING.value]
        ),
    )
    active_run = session.exec(statement).first()
    if active_run is not None:
        if active_run.generation == deployment.generation:
            return active_run
        raise HTTPException(status_code=409, detail="Deployment already has an active run")

    run = Run(
        id=new_id("run"),
        deployment_id=deployment.id,
        strategy_version_id=deployment.strategy_version_id,
        config_version_id=deployment.config_version_id,
        worker_id=deployment.worker_id,
        generation=deployment.generation,
        status=RunStatus.RUNNING.value,
        pid=pid,
        started_at=utc_now(),
    )
    deployment.actual_state = DeploymentState.RUNNING.value
    deployment.actual_revision = deployment.desired_revision
    deployment.updated_at = utc_now()
    session.add(run)

    statement = select(Command).where(
        Command.target_id == deployment.id,
        Command.desired_revision == deployment.desired_revision,
        Command.status.in_([CommandStatus.PENDING.value, CommandStatus.ACKED.value]),
    )
    command = session.exec(statement).first()
    complete_command(session, command, result={"run_id": run.id}, actor=actor)

    audit(
        session,
        "deployment_run_started",
        "run",
        run.id,
        after={"pid": pid},
        actor=actor,
    )
    return run


def stop_run_for_deployment(
    session: Session,
    deployment: Deployment,
    run_id: str | None,
    exit_code: int | None,
    error: str | None,
    command: Command | None = None,
    actor: str = "system",
) -> Run | None:
    statement = select(Run).where(
        Run.deployment_id == deployment.id,
        Run.status.in_(
            [RunStatus.STARTING.value, RunStatus.RUNNING.value, RunStatus.STOPPING.value]
        ),
    )
    if run_id:
        statement = statement.where(Run.id == run_id)
    run = session.exec(statement).first()
    if run is not None:
        run.status = RunStatus.FAILED.value if error else RunStatus.STOPPED.value
        run.exit_code = exit_code
        run.error = error
        run.ended_at = utc_now()
    deployment.actual_state = (
        DeploymentState.FAILED.value if error else DeploymentState.STOPPED.value
    )
    deployment.actual_revision = deployment.desired_revision
    deployment.updated_at = utc_now()
    complete_command(
        session,
        command,
        result={"run_id": run.id if run else None, "exit_code": exit_code},
        error=error,
        actor=actor,
    )
    audit(
        session,
        "deployment_run_stopped",
        "deployment",
        deployment.id,
        after={"run_id": run.id if run else None, "error": error},
        actor=actor,
    )
    return run
