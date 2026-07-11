import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

import httpx
import socketio

from infinex.worker.client import ControlPlaneClient

logger = logging.getLogger(__name__)


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, ensure_ascii=False, sort_keys=True))


@dataclass
class ManagedRunner:
    deployment_id: str
    generation: int
    process: subprocess.Popen[bytes]
    log_file: IO[bytes]
    run_id: str | None = None


class LiveAgent:
    def __init__(
        self,
        *,
        worker_id: str,
        control_plane_url: str,
        runtime_version: str,
        capacity: int,
        token: str,
        work_dir: Path,
        heartbeat_interval: float = 5.0,
        poll_interval: float = 2.0,
    ) -> None:
        self.worker_id = worker_id
        self.control_plane_url = control_plane_url.rstrip("/")
        self.runtime_version = runtime_version
        self.capacity = capacity
        self.token = token
        self.work_dir = work_dir
        self.heartbeat_interval = heartbeat_interval
        self.poll_interval = poll_interval
        self.credential_path = work_dir / "worker-token"
        effective_token = (
            self.credential_path.read_text(encoding="utf-8").strip()
            if self.credential_path.is_file()
            else token
        )
        self.client = ControlPlaneClient(self.control_plane_url, effective_token)
        self.runners: dict[str, ManagedRunner] = {}
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.socket = socketio.Client(reconnection=True, logger=False, engineio_logger=False)
        self._configure_socket()

    def _configure_socket(self) -> None:
        @self.socket.on("command.available")
        def on_command(_payload: dict[str, Any]) -> None:
            self.wake_event.set()

        @self.socket.event
        def connect() -> None:
            log_event("agent_socket_connected", worker_id=self.worker_id)
            self.wake_event.set()

        @self.socket.event
        def disconnect(reason: str | None = None) -> None:
            log_event("agent_socket_disconnected", worker_id=self.worker_id, reason=reason)

    def _connect_socket(self) -> None:
        if self.socket.connected:
            return
        try:
            self.socket.connect(
                self.control_plane_url,
                auth={"worker_id": self.worker_id, "token": self.token},
                socketio_path="socket.io",
                wait_timeout=3,
            )
        except (socketio.exceptions.ConnectionError, OSError) as exc:
            log_event("agent_socket_unavailable", worker_id=self.worker_id, error=str(exc))

    def _install_signal_handlers(self) -> None:
        def request_stop(_signum: int, _frame: Any) -> None:
            self.stop_event.set()
            self.wake_event.set()

        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)

    def register(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        response = self.client.register(
            worker_id=self.worker_id,
            role="live",
            runtime_version=self.runtime_version,
            capacity=self.capacity,
            metadata={"pid": os.getpid(), "transport": "http+socket.io"},
        )
        if response.get("worker_token"):
            self.credential_path.write_text(self.client.token, encoding="utf-8")
            self.credential_path.chmod(0o600)
        self.token = self.client.token
        log_event("agent_registered", worker_id=self.worker_id, role="live")

    def heartbeat(self) -> None:
        self.client.heartbeat(
            self.worker_id,
            runtime_version=self.runtime_version,
            capacity=self.capacity,
            current_runs=sum(item.process.poll() is None for item in self.runners.values()),
            metadata={"pid": os.getpid(), "transport": "http+socket.io"},
        )

    def _command_for_deployment(
        self,
        deployment: dict[str, Any],
        commands: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        matches = [
            command
            for command in commands
            if command["target_id"] == deployment["id"]
            and command.get("desired_revision") == deployment["desired_revision"]
        ]
        return matches[-1] if matches else None

    def _start_runner(
        self,
        deployment: dict[str, Any],
        command: dict[str, Any] | None,
    ) -> None:
        if len(self.runners) >= self.capacity:
            error = f"Worker capacity {self.capacity} reached"
            self.client.report_run_stopped(
                deployment["id"],
                worker_id=self.worker_id,
                run_id=None,
                exit_code=None,
                error=error,
                command_id=command["id"] if command else None,
            )
            log_event("runner_start_rejected", deployment_id=deployment["id"], error=error)
            return

        deployment_dir = self.work_dir / "deployments" / deployment["id"]
        deployment_dir.mkdir(parents=True, exist_ok=True)
        log_path = deployment_dir / f"generation-{deployment['generation']}.log"
        log_file = log_path.open("ab")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "infinex.runner",
                "live",
                "--deployment-id",
                deployment["id"],
                "--generation",
                str(deployment["generation"]),
            ],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        managed = ManagedRunner(
            deployment_id=deployment["id"],
            generation=deployment["generation"],
            process=process,
            log_file=log_file,
        )
        self.runners[deployment["id"]] = managed
        try:
            run = self.client.report_run_started(
                deployment["id"],
                worker_id=self.worker_id,
                pid=process.pid,
                command_id=command["id"] if command else None,
            )
            managed.run_id = run["id"]
        except Exception:
            process.terminate()
            process.wait(timeout=5)
            log_file.close()
            self.runners.pop(deployment["id"], None)
            raise
        log_event(
            "runner_started",
            deployment_id=deployment["id"],
            generation=deployment["generation"],
            pid=process.pid,
            run_id=managed.run_id,
        )

    def _stop_runner(
        self,
        deployment: dict[str, Any],
        command: dict[str, Any] | None,
    ) -> None:
        managed = self.runners.get(deployment["id"])
        exit_code: int | None = None
        if managed is not None:
            if managed.process.poll() is None:
                managed.process.terminate()
                try:
                    exit_code = managed.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    managed.process.kill()
                    exit_code = managed.process.wait(timeout=5)
            else:
                exit_code = managed.process.returncode
            managed.log_file.close()

        self.client.report_run_stopped(
            deployment["id"],
            worker_id=self.worker_id,
            run_id=managed.run_id if managed else None,
            exit_code=exit_code,
            error=None,
            command_id=command["id"] if command else None,
        )
        self.runners.pop(deployment["id"], None)
        log_event("runner_stopped", deployment_id=deployment["id"], exit_code=exit_code)

    def _report_unexpected_exits(self) -> None:
        for deployment_id, managed in list(self.runners.items()):
            exit_code = managed.process.poll()
            if exit_code is None:
                continue
            managed.log_file.close()
            error = f"Runner exited unexpectedly with code {exit_code}"
            try:
                self.client.report_run_stopped(
                    deployment_id,
                    worker_id=self.worker_id,
                    run_id=managed.run_id,
                    exit_code=exit_code,
                    error=error,
                    command_id=None,
                )
            except httpx.HTTPError as exc:
                log_event("runner_exit_report_failed", deployment_id=deployment_id, error=str(exc))
            self.runners.pop(deployment_id, None)
            log_event("runner_exited", deployment_id=deployment_id, exit_code=exit_code)

    def sync_once(self) -> None:
        self._report_unexpected_exits()
        desired = self.client.desired_state(self.worker_id)
        commands = desired.get("commands", [])
        for command in commands:
            if command["status"] == "pending":
                self.client.acknowledge(command["id"], self.worker_id)
                command["status"] = "acked"

        for deployment in desired.get("deployments", []):
            command = self._command_for_deployment(deployment, commands)
            managed = self.runners.get(deployment["id"])
            desired_state = deployment["desired_state"]

            if desired_state == "running":
                if managed and managed.generation != deployment["generation"]:
                    self._stop_runner(deployment, None)
                    managed = None
                if managed is None:
                    self._start_runner(deployment, command)
            elif desired_state in {"stopped", "created"}:
                if managed is not None or deployment["actual_state"] != desired_state:
                    self._stop_runner(deployment, command)

    def run(self, *, once: bool = False) -> None:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        logging.getLogger("httpx").setLevel(logging.WARNING)
        self._install_signal_handlers()
        self.register()
        if not once:
            self._connect_socket()

        last_heartbeat = 0.0
        try:
            while not self.stop_event.is_set():
                now = time.monotonic()
                try:
                    if now - last_heartbeat >= self.heartbeat_interval:
                        self.heartbeat()
                        last_heartbeat = now
                    self.sync_once()
                except (httpx.HTTPError, OSError, RuntimeError) as exc:
                    log_event("agent_sync_failed", worker_id=self.worker_id, error=str(exc))

                if once:
                    break
                self.wake_event.wait(self.poll_interval)
                self.wake_event.clear()
                if not self.socket.connected:
                    self._connect_socket()
        finally:
            if self.socket.connected:
                self.socket.disconnect()
            self.client.close()
