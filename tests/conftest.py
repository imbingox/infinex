import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/infinex-test-bootstrap.db")
os.environ.setdefault("ARTIFACT_DIR", "/tmp/infinex-test-artifacts")
os.environ.setdefault("WORKER_ENROLLMENT_TOKEN", "test-enrollment-token")

from infinex.control_plane.app import fastapi_app  # noqa: E402
from infinex.control_plane.db import get_session  # noqa: E402
from infinex.control_plane.settings import get_settings  # noqa: E402


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as test_session:
        yield test_session
    engine.dispose()


@pytest.fixture
def client(session: Session, tmp_path: Path) -> Generator[TestClient]:
    settings = get_settings()
    previous_artifact_dir = settings.artifact_dir
    settings.artifact_dir = tmp_path / "artifacts"

    def override_session() -> Generator[Session]:
        yield session

    fastapi_app.dependency_overrides[get_session] = override_session
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
    settings.artifact_dir = previous_artifact_dir


@pytest.fixture
def worker_headers() -> dict[str, str]:
    return {"X-Worker-Token": "test-enrollment-token"}
