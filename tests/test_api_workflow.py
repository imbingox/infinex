from fastapi.testclient import TestClient

RUNTIME = "py313-nautilus-mock"


def create_version(client: TestClient) -> tuple[dict, dict]:
    strategy = client.post(
        "/api/strategies",
        json={"name": "mean-reversion", "description": "test strategy"},
    ).json()
    draft_response = client.put(
        f"/api/strategies/{strategy['id']}/draft",
        json={
            "source_code": "class Strategy: pass\n",
            "entrypoint": "strategy:Strategy",
            "runtime_version": RUNTIME,
            "config_schema": {
                "type": "object",
                "properties": {"window": {"type": "integer", "minimum": 2}},
                "required": ["window"],
            },
            "defaults": {"window": 20},
        },
    )
    assert draft_response.status_code == 200
    version_response = client.post(
        f"/api/strategies/{strategy['id']}/versions",
        json={},
    )
    assert version_response.status_code == 201
    version = version_response.json()
    configs = client.get(
        "/api/config-versions",
        params={"strategy_version_id": version["id"]},
    ).json()
    return version, configs[0]


def test_platform_workflow(client: TestClient, worker_headers: dict[str, str]) -> None:
    health = client.get("/api/health")
    assert health.json() == {"status": "ok"}
    assert health.headers["X-Request-ID"]
    version, config = create_version(client)

    published = client.post(f"/api/strategy-versions/{version['id']}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    backtest_worker = client.post(
        "/api/workers/register",
        headers=worker_headers,
        json={
            "worker_id": "backtest-1",
            "role": "backtest",
            "runtime_version": RUNTIME,
            "capacity": 1,
        },
    )
    assert backtest_worker.status_code == 201
    assert backtest_worker.json()["metadata"] == {}
    backtest_headers = {"X-Worker-Token": backtest_worker.json()["worker_token"]}

    backtest = client.post(
        "/api/backtests",
        json={
            "strategy_version_id": version["id"],
            "config_version_id": config["id"],
            "dataset": "fixture-v1",
        },
    ).json()
    claim = client.post(
        "/api/workers/backtest-1/backtests/claim",
        headers=backtest_headers,
    )
    assert claim.status_code == 200
    assert claim.json()["run"]["id"] == backtest["id"]
    running = client.post(
        f"/api/backtests/{backtest['id']}/running",
        headers=backtest_headers,
        json={"worker_id": "backtest-1", "lease_seconds": 300},
    )
    assert running.json()["status"] == "running"
    completed = client.post(
        f"/api/backtests/{backtest['id']}/complete",
        headers=backtest_headers,
        json={"worker_id": "backtest-1", "result": {"metrics": {"total_return": 0.1}}},
    )
    assert completed.json()["status"] == "succeeded"

    live_worker = client.post(
        "/api/workers/register",
        headers=worker_headers,
        json={
            "worker_id": "live-1",
            "role": "live",
            "runtime_version": RUNTIME,
            "capacity": 2,
        },
    )
    assert live_worker.status_code == 201
    live_headers = {"X-Worker-Token": live_worker.json()["worker_token"]}
    deployment_response = client.post(
        "/api/deployments",
        json={
            "name": "paper-mean-reversion",
            "worker_id": "live-1",
            "strategy_version_id": version["id"],
            "config_version_id": config["id"],
            "account_ref": "paper-account-1",
        },
    )
    assert deployment_response.status_code == 201
    deployment = deployment_response.json()

    start = client.post(f"/api/deployments/{deployment['id']}/start").json()
    start_command = start["command"]
    desired = client.get(
        "/api/workers/live-1/desired-state",
        headers=live_headers,
    ).json()
    assert desired["deployments"][0]["desired_state"] == "running"
    assert desired["commands"][0]["id"] == start_command["id"]
    client.post(
        f"/api/commands/{start_command['id']}/ack",
        headers=live_headers,
        json={"worker_id": "live-1"},
    )
    started = client.post(
        f"/api/deployments/{deployment['id']}/agent/started",
        headers=live_headers,
        json={"worker_id": "live-1", "pid": 12345, "command_id": start_command["id"]},
    )
    assert started.status_code == 200
    run = started.json()
    assert run["status"] == "running"

    stop = client.post(f"/api/deployments/{deployment['id']}/stop").json()
    stop_command = stop["command"]
    client.post(
        f"/api/commands/{stop_command['id']}/ack",
        headers=live_headers,
        json={"worker_id": "live-1"},
    )
    stopped = client.post(
        f"/api/deployments/{deployment['id']}/agent/stopped",
        headers=live_headers,
        json={
            "worker_id": "live-1",
            "run_id": run["id"],
            "exit_code": 0,
            "command_id": stop_command["id"],
        },
    )
    assert stopped.status_code == 200
    assert stopped.json()["deployment"]["actual_state"] == "stopped"

    summary = client.get("/api/summary").json()
    assert summary["workers"]["total"] == 2
    assert summary["backtests"]["succeeded"] == 1
    assert len(client.get("/api/audit-events").json()) >= 10


def test_worker_endpoints_require_token(client: TestClient) -> None:
    response = client.post(
        "/api/workers/register",
        json={"worker_id": "unauthorized", "role": "live"},
    )
    assert response.status_code == 401


def test_worker_credential_cannot_impersonate_another_worker(
    client: TestClient,
    worker_headers: dict[str, str],
) -> None:
    first = client.post(
        "/api/workers/register",
        headers=worker_headers,
        json={"worker_id": "identity-1", "role": "live"},
    ).json()
    client.post(
        "/api/workers/register",
        headers=worker_headers,
        json={"worker_id": "identity-2", "role": "live"},
    )
    response = client.post(
        "/api/workers/identity-2/heartbeat",
        headers={"X-Worker-Token": first["worker_token"]},
        json={"current_runs": 0},
    )
    assert response.status_code == 401


def test_invalid_config_is_rejected(client: TestClient) -> None:
    version, _config = create_version(client)
    response = client.post(
        f"/api/strategy-versions/{version['id']}/configs",
        json={"config": {"window": 1}},
    )
    assert response.status_code == 422
