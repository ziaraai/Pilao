"""Visible status of background jobs (``jobs`` table), shared by every worker task."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Job
from app.services import credits


def set_job_status(
    db: Session, kind: str, ref_id: uuid.UUID, status: str, error: str | None = None
) -> None:
    """Update the latest job of ``kind`` for ``ref_id`` (no-op if none). Caller commits."""
    job = db.scalars(
        select(Job).where(Job.kind == kind, Job.ref_id == ref_id).order_by(Job.created_at.desc())
    ).first()
    if job is None:
        return
    now = datetime.now(UTC)
    job.status, job.error = status, error
    if status == "running":
        job.started_at = now
    if status in ("done", "error"):
        job.finished_at = now
        if status == "done":
            job.progress = 100
    if status == "error":
        credits.refund_failed(db, job)  # lot 4: a failed work gives its credits back
