from typing import Any

import socketio
from sqlmodel import Session

from infinex.control_plane.db import get_engine
from infinex.control_plane.models import Worker
from infinex.control_plane.security import verify_worker_token

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)


@sio.event
async def connect(sid: str, _environ: dict[str, Any], auth: dict[str, Any] | None) -> bool:
    auth = auth or {}
    worker_id = auth.get("worker_id")
    if worker_id:
        with Session(get_engine()) as session:
            worker = session.get(Worker, worker_id)
            if worker is None or not verify_worker_token(
                str(auth.get("token", "")),
                worker.credential_hash,
            ):
                return False
        await sio.save_session(sid, {"worker_id": worker_id})
        await sio.enter_room(sid, f"worker:{worker_id}")
    return True


@sio.event
async def disconnect(_sid: str, _reason: str | None = None) -> None:
    return None


async def publish_update(
    resource: str,
    action: str,
    object_id: str,
    *,
    worker_id: str | None = None,
) -> None:
    payload = {
        "resource": resource,
        "action": action,
        "object_id": object_id,
    }
    await sio.emit("system.updated", payload)
    if worker_id:
        await sio.emit("command.available", payload, room=f"worker:{worker_id}")
