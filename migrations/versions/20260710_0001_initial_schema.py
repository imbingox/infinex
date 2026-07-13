"""Create the initial Infinex control-plane schema.

Revision ID: 20260710_0001
Revises:
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260710_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auditevent",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("object_type", sa.String(), nullable=False),
        sa.Column("object_id", sa.String(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "command",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("worker_id", sa.String(), nullable=True),
        sa.Column("desired_revision", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_command_message_id"),
    )
    op.create_index(op.f("ix_command_message_id"), "command", ["message_id"], unique=False)
    op.create_index(op.f("ix_command_status"), "command", ["status"], unique=False)
    op.create_index(op.f("ix_command_target_id"), "command", ["target_id"], unique=False)
    op.create_index(op.f("ix_command_worker_id"), "command", ["worker_id"], unique=False)
    op.create_table(
        "strategy",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("owner", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_strategy_name"),
    )
    op.create_index(op.f("ix_strategy_name"), "strategy", ["name"], unique=False)
    op.create_table(
        "worker",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("runtime_version", sa.String(), nullable=False),
        sa.Column("credential_hash", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("current_runs", sa.Integer(), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_worker_role"), "worker", ["role"], unique=False)
    op.create_index(op.f("ix_worker_status"), "worker", ["status"], unique=False)
    op.create_table(
        "strategydraft",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("strategy_id", sa.String(), nullable=False),
        sa.Column("source_code", sa.Text(), nullable=True),
        sa.Column("entrypoint", sa.String(), nullable=False),
        sa.Column("runtime_version", sa.String(), nullable=False),
        sa.Column("config_schema", sa.JSON(), nullable=True),
        sa.Column("defaults", sa.JSON(), nullable=True),
        sa.Column("source_ref", sa.JSON(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategy.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_strategydraft_strategy_id"),
        "strategydraft",
        ["strategy_id"],
        unique=False,
    )
    op.create_table(
        "strategyversion",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("strategy_id", sa.String(), nullable=False),
        sa.Column("version_label", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source_snapshot_sha256", sa.String(), nullable=False),
        sa.Column("artifact_sha256", sa.String(), nullable=True),
        sa.Column("artifact_path", sa.String(), nullable=True),
        sa.Column("entrypoint", sa.String(), nullable=False),
        sa.Column("runtime_version", sa.String(), nullable=False),
        sa.Column("config_schema", sa.JSON(), nullable=True),
        sa.Column("defaults", sa.JSON(), nullable=True),
        sa.Column("source_ref", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategy.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_strategyversion_status"),
        "strategyversion",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_strategyversion_strategy_id"),
        "strategyversion",
        ["strategy_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_strategyversion_version_label"),
        "strategyversion",
        ["version_label"],
        unique=False,
    )
    op.create_table(
        "configversion",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("strategy_version_id", sa.String(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("config_hash", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["strategy_version_id"], ["strategyversion.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_configversion_config_hash"),
        "configversion",
        ["config_hash"],
        unique=False,
    )
    op.create_index(
        op.f("ix_configversion_strategy_version_id"),
        "configversion",
        ["strategy_version_id"],
        unique=False,
    )
    op.create_table(
        "backtestrun",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("strategy_version_id", sa.String(), nullable=False),
        sa.Column("config_version_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("dataset", sa.String(), nullable=False),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("worker_id", sa.String(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["config_version_id"], ["configversion.id"]),
        sa.ForeignKeyConstraint(["strategy_version_id"], ["strategyversion.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["worker.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_backtestrun_config_version_id"),
        "backtestrun",
        ["config_version_id"],
        unique=False,
    )
    op.create_index(op.f("ix_backtestrun_status"), "backtestrun", ["status"], unique=False)
    op.create_index(
        op.f("ix_backtestrun_strategy_version_id"),
        "backtestrun",
        ["strategy_version_id"],
        unique=False,
    )
    op.create_table(
        "deployment",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("worker_id", sa.String(), nullable=False),
        sa.Column("strategy_version_id", sa.String(), nullable=False),
        sa.Column("config_version_id", sa.String(), nullable=False),
        sa.Column("account_ref", sa.String(), nullable=False),
        sa.Column("desired_state", sa.String(), nullable=False),
        sa.Column("actual_state", sa.String(), nullable=False),
        sa.Column("desired_revision", sa.Integer(), nullable=False),
        sa.Column("actual_revision", sa.Integer(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["config_version_id"], ["configversion.id"]),
        sa.ForeignKeyConstraint(["strategy_version_id"], ["strategyversion.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["worker.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_deployment_actual_state"),
        "deployment",
        ["actual_state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deployment_config_version_id"),
        "deployment",
        ["config_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deployment_desired_state"),
        "deployment",
        ["desired_state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deployment_strategy_version_id"),
        "deployment",
        ["strategy_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deployment_worker_id"),
        "deployment",
        ["worker_id"],
        unique=False,
    )
    op.create_table(
        "run",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("deployment_id", sa.String(), nullable=False),
        sa.Column("strategy_version_id", sa.String(), nullable=False),
        sa.Column("config_version_id", sa.String(), nullable=False),
        sa.Column("worker_id", sa.String(), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["config_version_id"], ["configversion.id"]),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployment.id"]),
        sa.ForeignKeyConstraint(["strategy_version_id"], ["strategyversion.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["worker.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_run_config_version_id"), "run", ["config_version_id"], unique=False)
    op.create_index(op.f("ix_run_deployment_id"), "run", ["deployment_id"], unique=False)
    op.create_index(op.f("ix_run_status"), "run", ["status"], unique=False)
    op.create_index(
        op.f("ix_run_strategy_version_id"), "run", ["strategy_version_id"], unique=False
    )
    op.create_index(op.f("ix_run_worker_id"), "run", ["worker_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_run_worker_id"), table_name="run")
    op.drop_index(op.f("ix_run_strategy_version_id"), table_name="run")
    op.drop_index(op.f("ix_run_status"), table_name="run")
    op.drop_index(op.f("ix_run_deployment_id"), table_name="run")
    op.drop_index(op.f("ix_run_config_version_id"), table_name="run")
    op.drop_table("run")
    op.drop_index(op.f("ix_deployment_worker_id"), table_name="deployment")
    op.drop_index(op.f("ix_deployment_strategy_version_id"), table_name="deployment")
    op.drop_index(op.f("ix_deployment_desired_state"), table_name="deployment")
    op.drop_index(op.f("ix_deployment_config_version_id"), table_name="deployment")
    op.drop_index(op.f("ix_deployment_actual_state"), table_name="deployment")
    op.drop_table("deployment")
    op.drop_index(op.f("ix_backtestrun_strategy_version_id"), table_name="backtestrun")
    op.drop_index(op.f("ix_backtestrun_status"), table_name="backtestrun")
    op.drop_index(op.f("ix_backtestrun_config_version_id"), table_name="backtestrun")
    op.drop_table("backtestrun")
    op.drop_index(op.f("ix_configversion_strategy_version_id"), table_name="configversion")
    op.drop_index(op.f("ix_configversion_config_hash"), table_name="configversion")
    op.drop_table("configversion")
    op.drop_index(op.f("ix_strategyversion_version_label"), table_name="strategyversion")
    op.drop_index(op.f("ix_strategyversion_strategy_id"), table_name="strategyversion")
    op.drop_index(op.f("ix_strategyversion_status"), table_name="strategyversion")
    op.drop_table("strategyversion")
    op.drop_index(op.f("ix_strategydraft_strategy_id"), table_name="strategydraft")
    op.drop_table("strategydraft")
    op.drop_index(op.f("ix_worker_status"), table_name="worker")
    op.drop_index(op.f("ix_worker_role"), table_name="worker")
    op.drop_table("worker")
    op.drop_index(op.f("ix_strategy_name"), table_name="strategy")
    op.drop_table("strategy")
    op.drop_index(op.f("ix_command_worker_id"), table_name="command")
    op.drop_index(op.f("ix_command_target_id"), table_name="command")
    op.drop_index(op.f("ix_command_status"), table_name="command")
    op.drop_index(op.f("ix_command_message_id"), table_name="command")
    op.drop_table("command")
    op.drop_table("auditevent")
