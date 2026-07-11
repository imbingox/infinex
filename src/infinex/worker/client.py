from pathlib import Path
from typing import Any

import httpx


class ControlPlaneClient:
    def __init__(self, base_url: str, token: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"X-Worker-Token": token},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def register(
        self,
        *,
        worker_id: str,
        role: str,
        runtime_version: str,
        capacity: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            "/api/workers/register",
            json={
                "worker_id": worker_id,
                "role": role,
                "runtime_version": runtime_version,
                "capacity": capacity,
                "metadata": metadata or {},
            },
        )
        response.raise_for_status()
        payload = response.json()
        if worker_token := payload.get("worker_token"):
            self.token = worker_token
            self._client.headers["X-Worker-Token"] = worker_token
        return payload

    def heartbeat(
        self,
        worker_id: str,
        *,
        runtime_version: str,
        capacity: int,
        current_runs: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/api/workers/{worker_id}/heartbeat",
            json={
                "runtime_version": runtime_version,
                "capacity": capacity,
                "current_runs": current_runs,
                "metadata": metadata,
            },
        )
        response.raise_for_status()
        return response.json()

    def desired_state(self, worker_id: str) -> dict[str, Any]:
        response = self._client.get(f"/api/workers/{worker_id}/desired-state")
        response.raise_for_status()
        return response.json()

    def acknowledge(self, command_id: str, worker_id: str) -> dict[str, Any]:
        response = self._client.post(
            f"/api/commands/{command_id}/ack",
            json={"worker_id": worker_id},
        )
        response.raise_for_status()
        return response.json()

    def report_run_started(
        self,
        deployment_id: str,
        *,
        worker_id: str,
        pid: int,
        command_id: str | None,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/api/deployments/{deployment_id}/agent/started",
            json={
                "worker_id": worker_id,
                "pid": pid,
                "command_id": command_id,
            },
        )
        response.raise_for_status()
        return response.json()

    def report_run_stopped(
        self,
        deployment_id: str,
        *,
        worker_id: str,
        run_id: str | None,
        exit_code: int | None,
        error: str | None,
        command_id: str | None,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/api/deployments/{deployment_id}/agent/stopped",
            json={
                "worker_id": worker_id,
                "run_id": run_id,
                "exit_code": exit_code,
                "error": error,
                "command_id": command_id,
            },
        )
        response.raise_for_status()
        return response.json()

    def claim_backtest(self, worker_id: str) -> dict[str, Any] | None:
        response = self._client.post(f"/api/workers/{worker_id}/backtests/claim")
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json()

    def mark_backtest_running(self, run_id: str, worker_id: str) -> dict[str, Any]:
        response = self._client.post(
            f"/api/backtests/{run_id}/running",
            json={"worker_id": worker_id, "lease_seconds": 300},
        )
        response.raise_for_status()
        return response.json()

    def complete_backtest(
        self,
        run_id: str,
        *,
        worker_id: str,
        result: dict[str, Any],
        error: str | None,
    ) -> dict[str, Any]:
        response = self._client.post(
            f"/api/backtests/{run_id}/complete",
            json={"worker_id": worker_id, "result": result, "error": error},
        )
        response.raise_for_status()
        return response.json()

    def download(self, path: str, destination: Path) -> str | None:
        response = self._client.get(path)
        response.raise_for_status()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return response.headers.get("etag", "").strip('"') or None
