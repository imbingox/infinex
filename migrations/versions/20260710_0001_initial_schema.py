"""Create the initial Infinex control-plane schema.

Revision ID: 20260710_0001
Revises:
Create Date: 2026-07-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlmodel import SQLModel

from infinex.control_plane import models  # noqa: F401

revision: str = "20260710_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    if not tables:
        SQLModel.metadata.create_all(bind)
        return

    if "worker" in tables:
        worker_columns = {column["name"] for column in inspector.get_columns("worker")}
        if "credential_hash" not in worker_columns:
            op.add_column("worker", sa.Column("credential_hash", sa.String(), nullable=True))


def downgrade() -> None:
    SQLModel.metadata.drop_all(op.get_bind())
