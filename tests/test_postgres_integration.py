import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlmodel import Session, create_engine, select

from infinex.control_plane.models import Worker
from infinex.control_plane.security import hash_worker_token


@pytest.mark.postgres
def test_postgres_migration_and_worker_roundtrip() -> None:
    database_url = os.getenv("TEST_POSTGRES_URL")
    if not database_url:
        pytest.skip("TEST_POSTGRES_URL is not configured")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    engine = create_engine(database_url)
    assert "worker" in inspect(engine).get_table_names()
    worker = Worker(
        id="postgres-integration-worker",
        role="live",
        runtime_version="py313-nautilus-mock",
        credential_hash=hash_worker_token("postgres-test-token"),
    )
    with Session(engine) as session:
        existing = session.get(Worker, worker.id)
        if existing:
            session.delete(existing)
            session.commit()
        session.add(worker)
        session.commit()
        loaded = session.exec(select(Worker).where(Worker.id == worker.id)).one()
        assert loaded.runtime_version == "py313-nautilus-mock"
        session.delete(loaded)
        session.commit()
    engine.dispose()
