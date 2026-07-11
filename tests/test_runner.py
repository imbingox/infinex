from pathlib import Path

from infinex.runner.mock import deterministic_backtest, verify_bundle


def test_deterministic_backtest_is_reproducible() -> None:
    arguments = {
        "strategy_version_id": "sv_test",
        "config_hash": "abc123",
        "dataset": "fixture-v1",
        "start_time": None,
        "end_time": None,
    }
    first = deterministic_backtest(**arguments)
    second = deterministic_backtest(**arguments)
    assert first == second
    assert first["metrics"]["trade_count"] > 0


def test_bundle_created_by_api_is_valid(client, tmp_path: Path) -> None:
    strategy = client.post("/api/strategies", json={"name": "bundle-test"}).json()
    client.put(
        f"/api/strategies/{strategy['id']}/draft",
        json={
            "source_code": "class Strategy: pass\n",
            "entrypoint": "strategy:Strategy",
            "defaults": {},
        },
    )
    version = client.post(f"/api/strategies/{strategy['id']}/versions", json={}).json()
    artifact = client.get(f"/api/strategy-versions/{version['id']}/artifact")
    path = tmp_path / "bundle.zip"
    path.write_bytes(artifact.content)
    manifest = verify_bundle(path)
    assert manifest["strategy_version_id"] == version["id"]
