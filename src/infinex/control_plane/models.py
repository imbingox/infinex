from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, Text, UniqueConstraint
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrategyVersionStatus(StrEnum):
    CANDIDATE = "candidate"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class WorkerRole(StrEnum):
    BACKTEST = "backtest"
    LIVE = "live"


class WorkerStatus(StrEnum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class BacktestStatus(StrEnum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    LEASE_EXPIRED = "lease_expired"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DeploymentState(StrEnum):
    CREATED = "created"
    PREPARING = "preparing"
    READY = "ready"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class RunStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class CommandStatus(StrEnum):
    PENDING = "pending"
    ACKED = "acked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Strategy(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("name", name="uq_strategy_name"),)

    id: str = Field(default_factory=lambda: new_id("strat"), primary_key=True)
    name: str = Field(index=True)
    description: str | None = None
    owner: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class StrategyDraft(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("draft"), primary_key=True)
    strategy_id: str = Field(foreign_key="strategy.id", index=True)
    source_code: str = Field(sa_column=Column(Text))
    entrypoint: str
    runtime_version: str
    config_schema: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    defaults: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    source_ref: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    notes: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class StrategyVersion(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("sv"), primary_key=True)
    strategy_id: str = Field(foreign_key="strategy.id", index=True)
    version_label: str = Field(index=True)
    status: str = Field(default=StrategyVersionStatus.CANDIDATE.value, index=True)
    source_snapshot_sha256: str
    artifact_sha256: str | None = None
    artifact_path: str | None = None
    entrypoint: str
    runtime_version: str
    config_schema: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    defaults: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    source_ref: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    published_at: datetime | None = None


class ConfigVersion(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("cv"), primary_key=True)
    strategy_version_id: str = Field(foreign_key="strategyversion.id", index=True)
    config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    config_hash: str = Field(index=True)
    source: str = "manual"
    created_at: datetime = Field(default_factory=utc_now)


class Worker(SQLModel, table=True):
    id: str = Field(primary_key=True)
    role: str = Field(index=True)
    runtime_version: str
    credential_hash: str | None = Field(default=None, exclude=True)
    status: str = Field(default=WorkerStatus.ONLINE.value, index=True)
    capacity: int = 1
    current_runs: int = 0
    last_heartbeat_at: datetime = Field(default_factory=utc_now)
    metadata_json: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON),
    )
    created_at: datetime = Field(default_factory=utc_now)


class BacktestRun(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("bt"), primary_key=True)
    strategy_version_id: str = Field(foreign_key="strategyversion.id", index=True)
    config_version_id: str = Field(foreign_key="configversion.id", index=True)
    status: str = Field(default=BacktestStatus.QUEUED.value, index=True)
    dataset: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    worker_id: str | None = Field(default=None, foreign_key="worker.id")
    lease_expires_at: datetime | None = None
    result: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Deployment(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("dep"), primary_key=True)
    name: str
    worker_id: str = Field(foreign_key="worker.id", index=True)
    strategy_version_id: str = Field(foreign_key="strategyversion.id", index=True)
    config_version_id: str = Field(foreign_key="configversion.id", index=True)
    account_ref: str
    desired_state: str = Field(default=DeploymentState.CREATED.value, index=True)
    actual_state: str = Field(default=DeploymentState.CREATED.value, index=True)
    desired_revision: int = 0
    actual_revision: int = 0
    generation: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Run(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("run"), primary_key=True)
    deployment_id: str = Field(foreign_key="deployment.id", index=True)
    strategy_version_id: str = Field(foreign_key="strategyversion.id", index=True)
    config_version_id: str = Field(foreign_key="configversion.id", index=True)
    worker_id: str = Field(foreign_key="worker.id", index=True)
    generation: int
    status: str = Field(default=RunStatus.STARTING.value, index=True)
    pid: int | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    exit_code: int | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class Command(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("message_id", name="uq_command_message_id"),)

    id: str = Field(default_factory=lambda: new_id("cmd"), primary_key=True)
    message_id: str = Field(default_factory=lambda: uuid4().hex, index=True)
    type: str
    target_type: str
    target_id: str = Field(index=True)
    worker_id: str | None = Field(default=None, index=True)
    desired_revision: int | None = None
    status: str = Field(default=CommandStatus.PENDING.value, index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    result: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class AuditEvent(SQLModel, table=True):
    id: str = Field(default_factory=lambda: new_id("audit"), primary_key=True)
    actor: str = "system"
    action: str
    object_type: str
    object_id: str
    before: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    after: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
