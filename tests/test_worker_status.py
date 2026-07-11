from datetime import timedelta

from sqlmodel import Session

from infinex.control_plane.models import Worker, WorkerStatus, utc_now
from infinex.control_plane.services import sweep_worker_statuses


def test_status_sweep_persists_offline_transition(session: Session) -> None:
    worker = Worker(
        id="stale-worker",
        role="live",
        runtime_version="py313-nautilus-mock",
        last_heartbeat_at=utc_now() - timedelta(seconds=60),
    )
    session.add(worker)
    session.commit()

    changed = sweep_worker_statuses(session, offline_after_seconds=30)
    session.commit()
    session.refresh(worker)

    assert [item.id for item in changed] == [worker.id]
    assert worker.status == WorkerStatus.OFFLINE.value
