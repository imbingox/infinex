import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import httpx

from infinex.worker.client import ControlPlaneClient

logger = logging.getLogger(__name__)


def log_event(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, ensure_ascii=False, sort_keys=True))


class BacktestWorker:
    def __init__(
        self,
        *,
        worker_id: str,
        control_plane_url: str,
        runtime_version: str,
        token: str,
        work_dir: Path,
        poll_interval: float = 2.0,
    ) -> None:
        self.worker_id = worker_id
        self.runtime_version = runtime_version
        self.work_dir = work_dir
        self.poll_interval = poll_interval
        self.credential_path = work_dir / "worker-token"
        effective_token = (
            self.credential_path.read_text(encoding="utf-8").strip()
            if self.credential_path.is_file()
            else token
        )
        self.client = ControlPlaneClient(control_plane_url, effective_token, timeout=30.0)
        self.stop_event = threading.Event()

    def _install_signal_handlers(self) -> None:
        def request_stop(_signum: int, _frame: Any) -> None:
            self.stop_event.set()

        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)

    def register(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        response = self.client.register(
            worker_id=self.worker_id,
            role="backtest",
            runtime_version=self.runtime_version,
            capacity=1,
            metadata={"pid": os.getpid(), "runner": "deterministic-mock"},
        )
        if response.get("worker_token"):
            self.credential_path.write_text(self.client.token, encoding="utf-8")
            self.credential_path.chmod(0o600)
        log_event("backtest_worker_registered", worker_id=self.worker_id)

    def heartbeat(self, current_runs: int) -> None:
        self.client.heartbeat(
            self.worker_id,
            runtime_version=self.runtime_version,
            capacity=1,
            current_runs=current_runs,
            metadata={"pid": os.getpid(), "runner": "deterministic-mock"},
        )

    def _execute(self, claim: dict[str, Any]) -> None:
        run = claim["run"]
        version = claim["strategy_version"]
        config = claim["config_version"]
        run_dir = self.work_dir / "backtests" / run["id"]
        run_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = run_dir / "strategy.zip"
        self.client.download(claim["artifact_url"], bundle_path)
        actual_sha = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        if actual_sha != version["artifact_sha256"]:
            raise RuntimeError(
                f"Artifact SHA-256 mismatch: {actual_sha} != {version['artifact_sha256']}"
            )

        self.client.mark_backtest_running(run["id"], self.worker_id)
        output_path = run_dir / "result.json"
        command = [
            sys.executable,
            "-m",
            "infinex.runner",
            "backtest",
            "--strategy-version-id",
            version["id"],
            "--config-hash",
            config["config_hash"],
            "--dataset",
            run["dataset"],
            "--bundle",
            str(bundle_path),
            "--output",
            str(output_path),
        ]
        if run.get("start_time"):
            command.extend(["--start-time", run["start_time"]])
        if run.get("end_time"):
            command.extend(["--end-time", run["end_time"]])

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            check=False,
        )
        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(error[-4000:] or f"Runner exited with code {completed.returncode}")
        result = json.loads(output_path.read_text(encoding="utf-8"))
        self.client.complete_backtest(
            run["id"],
            worker_id=self.worker_id,
            result=result,
            error=None,
        )
        log_event("backtest_succeeded", worker_id=self.worker_id, run_id=run["id"])

    def run(self, *, once: bool = False) -> None:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        logging.getLogger("httpx").setLevel(logging.WARNING)
        self._install_signal_handlers()
        self.register()
        try:
            while not self.stop_event.is_set():
                try:
                    self.heartbeat(0)
                    claim = self.client.claim_backtest(self.worker_id)
                    if claim is not None:
                        self.heartbeat(1)
                        try:
                            self._execute(claim)
                        except Exception as exc:
                            run_id = claim["run"]["id"]
                            self.client.complete_backtest(
                                run_id,
                                worker_id=self.worker_id,
                                result={},
                                error=str(exc),
                            )
                            log_event(
                                "backtest_failed",
                                worker_id=self.worker_id,
                                run_id=run_id,
                                error=str(exc),
                            )
                except (httpx.HTTPError, OSError, RuntimeError) as exc:
                    log_event(
                        "backtest_worker_sync_failed", worker_id=self.worker_id, error=str(exc)
                    )

                if once:
                    break
                self.stop_event.wait(self.poll_interval)
        finally:
            self.client.close()
