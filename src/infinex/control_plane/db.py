from collections.abc import Generator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from infinex.control_plane.settings import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        if settings.database_url.startswith("sqlite:///"):
            db_path = settings.database_url.removeprefix("sqlite:///")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            _engine = create_engine(
                settings.database_url,
                connect_args={"check_same_thread": False},
            )

            @event.listens_for(_engine, "connect")
            def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        else:
            _engine = create_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def init_db() -> None:
    project_root = Path(__file__).resolve().parents[3]
    config = Config(project_root / "alembic.ini")
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(config, "head")


def get_session() -> Generator[Session]:
    with Session(get_engine()) as session:
        yield session


def reset_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None
