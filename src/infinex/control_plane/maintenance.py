import asyncio
import logging

from sqlmodel import Session

from infinex.control_plane.db import get_engine
from infinex.control_plane.realtime import publish_update
from infinex.control_plane.services import sweep_worker_statuses
from infinex.control_plane.settings import get_settings

logger = logging.getLogger(__name__)


async def worker_status_loop() -> None:
    settings = get_settings()
    while True:
        try:
            with Session(get_engine()) as session:
                changed = sweep_worker_statuses(
                    session,
                    settings.worker_offline_after_seconds,
                )
                if changed:
                    session.commit()
            for worker in changed:
                await publish_update("worker", "status_changed", worker.id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("worker_status_sweep_failed")
        await asyncio.sleep(settings.worker_status_sweep_interval_seconds)
