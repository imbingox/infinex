from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    owner: str | None = None


class StrategyDraftUpdate(BaseModel):
    source_code: str = Field(min_length=1)
    entrypoint: str = Field(min_length=1)
    runtime_version: str = "py313-nautilus-mock"
    config_schema: dict[str, Any] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    source_ref: dict[str, Any] = Field(default_factory=dict)


class StrategyVersionCreate(BaseModel):
    source_ref: dict[str, Any] = Field(default_factory=dict)


class ConfigVersionCreate(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    source: str = "manual"


class BacktestCreate(BaseModel):
    strategy_version_id: str
    config_version_id: str
    dataset: str = "local-demo"
    start_time: datetime | None = None
    end_time: datetime | None = None


class WorkerRegister(BaseModel):
    worker_id: str
    role: Literal["backtest", "live"]
    runtime_version: str = "py313-nautilus-mock"
    capacity: int = Field(default=1, ge=1, le=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerHeartbeat(BaseModel):
    runtime_version: str | None = None
    capacity: int | None = Field(default=None, ge=1, le=128)
    current_runs: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None


class DeploymentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    worker_id: str
    strategy_version_id: str
    config_version_id: str
    account_ref: str


class AgentRunStarted(BaseModel):
    worker_id: str
    pid: int | None = None
    command_id: str | None = None


class AgentRunStopped(BaseModel):
    worker_id: str
    run_id: str | None = None
    exit_code: int | None = None
    error: str | None = None
    command_id: str | None = None


class CommandAck(BaseModel):
    worker_id: str


class BacktestResultReport(BaseModel):
    worker_id: str
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class BacktestLeaseRenew(BaseModel):
    worker_id: str
    lease_seconds: int = Field(default=300, ge=30, le=3600)
