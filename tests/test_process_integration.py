import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Generator
from pathlib import Path

import httpx
import pytest

RUNTIME = "py313-nautilus-mock"


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_until(
    predicate: Callable[[], object],
    *,
    timeout: float = 15.0,
    interval: float = 0.2,
) -> object:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if result := predicate():
                return result
        except (httpx.HTTPError, KeyError, IndexError, OSError) as exc:
            last_error = exc
        time.sleep(interval)
    if last_error:
        raise AssertionError("Condition did not become true") from last_error
    raise AssertionError("Condition did not become true")


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture
def process_environment(tmp_path: Path) -> dict[str, str]:
    return {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'process.db'}",
        "ARTIFACT_DIR": str(tmp_path / "artifacts"),
        "WORKER_DATA_DIR": str(tmp_path / "workers"),
        "WORKER_ENROLLMENT_TOKEN": "process-enrollment-token",
        "WORKER_OFFLINE_AFTER_SECONDS": "2",
        "WORKER_STATUS_SWEEP_INTERVAL_SECONDS": "0.25",
        "WORKER_HEARTBEAT_INTERVAL_SECONDS": "0.5",
        "WORKER_POLL_INTERVAL_SECONDS": "0.25",
        "PYTHONUNBUFFERED": "1",
    }


@pytest.fixture
def running_platform(
    tmp_path: Path,
    process_environment: dict[str, str],
) -> Generator[tuple[str, subprocess.Popen[bytes], subprocess.Popen[bytes], Path]]:
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    server_log = (tmp_path / "server.log").open("ab")
    agent_log_path = tmp_path / "agent.log"
    agent_log = agent_log_path.open("ab")
    server_environment = {
        **process_environment,
        "INFINEX_PORT": str(port),
    }

    def start_server() -> subprocess.Popen[bytes]:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "infinex.cli",
                "serve",
                "--host",
                "127.0.0.1",
            ],
            env=server_environment,
            stdout=server_log,
            stderr=subprocess.STDOUT,
        )
        wait_until(lambda: httpx.get(f"{base_url}/api/health", timeout=1).status_code == 200)
        return process

    server = start_server()
    work_dir = tmp_path / "live-agent"
    agent_environment = {
        **process_environment,
        "CONTROL_PLANE_URL": base_url,
        "WORKER_ID": "live-process",
    }
    agent = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "infinex.cli",
            "live-agent",
            "--work-dir",
            str(work_dir),
        ],
        env=agent_environment,
        stdout=agent_log,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_until(
            lambda: any(
                worker["id"] == "live-process"
                for worker in httpx.get(f"{base_url}/api/workers", timeout=1).json()
            )
        )
        yield base_url, server, agent, agent_log_path
    finally:
        stop_process(agent)
        stop_process(server)
        agent_log.close()
        server_log.close()


def create_published_version(base_url: str) -> tuple[dict, dict]:
    client = httpx.Client(base_url=base_url, timeout=2)
    strategy = client.post("/api/strategies", json={"name": "process-strategy"}).json()
    client.put(
        f"/api/strategies/{strategy['id']}/draft",
        json={
            "source_code": "class Strategy: pass\n",
            "entrypoint": "strategy:Strategy",
            "runtime_version": RUNTIME,
            "defaults": {"window": 20},
        },
    ).raise_for_status()
    version = client.post(f"/api/strategies/{strategy['id']}/versions", json={}).json()
    client.post(f"/api/strategy-versions/{version['id']}/publish").raise_for_status()
    config = client.get(
        "/api/config-versions",
        params={"strategy_version_id": version["id"]},
    ).json()[0]
    client.close()
    return version, config


def test_live_agent_runner_and_socket_reconnect(
    running_platform,
    process_environment: dict[str, str],
) -> None:
    base_url, server, agent, agent_log_path = running_platform
    version, config = create_published_version(base_url)
    client = httpx.Client(base_url=base_url, timeout=2)
    deployment = client.post(
        "/api/deployments",
        json={
            "name": "process-deployment",
            "worker_id": "live-process",
            "strategy_version_id": version["id"],
            "config_version_id": config["id"],
            "account_ref": "process-account",
        },
    ).json()
    client.post(f"/api/deployments/{deployment['id']}/start").raise_for_status()

    running = wait_until(
        lambda: (
            item
            if (item := client.get(f"/api/deployments/{deployment['id']}").json())["actual_state"]
            == "running"
            else None
        )
    )
    run = client.get("/api/runs", params={"deployment_id": deployment["id"]}).json()[0]
    runner_pid = run["pid"]
    assert running["desired_state"] == "running"
    os.kill(runner_pid, 0)

    stop_process(server)
    time.sleep(0.8)
    os.kill(runner_pid, 0)

    port = int(base_url.rsplit(":", 1)[1])
    restarted_server_environment = {
        **process_environment,
        "INFINEX_PORT": str(port),
    }
    server_log = Path(agent_log_path).with_name("server-restarted.log").open("ab")
    restarted_server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "infinex.cli",
            "serve",
            "--host",
            "127.0.0.1",
        ],
        env=restarted_server_environment,
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_until(lambda: httpx.get(f"{base_url}/api/health", timeout=1).status_code == 200)
        wait_until(
            lambda: (
                agent_log_path.read_text(encoding="utf-8").count(
                    '"event": "agent_socket_connected"'
                )
                >= 2
            )
        )
        client = httpx.Client(base_url=base_url, timeout=2)
        client.post(f"/api/deployments/{deployment['id']}/stop").raise_for_status()
        wait_until(
            lambda: (
                client.get(f"/api/deployments/{deployment['id']}").json()["actual_state"]
                == "stopped"
            )
        )
        with pytest.raises(ProcessLookupError):
            os.kill(runner_pid, 0)
        credential_path = agent_log_path.parent / "live-agent" / "worker-token"
        assert credential_path.stat().st_mode & 0o777 == 0o600
        stop_process(agent)
        wait_until(
            lambda: (
                next(
                    worker
                    for worker in client.get("/api/workers").json()
                    if worker["id"] == "live-process"
                )["status"]
                == "offline"
            ),
            timeout=8,
        )
    finally:
        client.close()
        stop_process(restarted_server)
        server_log.close()
        if agent.poll() is None:
            agent.send_signal(signal.SIGTERM)
