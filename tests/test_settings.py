from pathlib import Path

from infinex.control_plane.settings import Settings


def test_settings_ignore_compose_and_cli_only_dotenv_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "INFINEX_PORT=8123\nWORKER_ID=backtest-node-01\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_file)

    assert settings.app_name == "Infinex Control Plane"
