from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Infinex Control Plane"
    database_url: str = "sqlite:///data/infinex.db"
    artifact_dir: Path = Path("data/artifacts")
    worker_data_dir: Path = Path("data/workers")
    web_dist_dir: Path = Path("web/dist")
    worker_enrollment_token: str = "development-enrollment-token"
    worker_offline_after_seconds: int = 30
    worker_status_sweep_interval_seconds: float = 5.0
    worker_heartbeat_interval_seconds: float = 5.0
    worker_poll_interval_seconds: float = 2.0
    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
