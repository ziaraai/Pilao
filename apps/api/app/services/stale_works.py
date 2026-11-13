"""Works left for dead (lot 4, final review C2).

A worker killed mid-job (out of memory, a redeploy), a timeout or every RQ retry spent leaves
an analysis, a chapter or a reading « en cours » for ever, with its credits taken. The sweep,
run every 15 minutes by ``app/workers/cron.py``, closes them as failed, which gives their
credits back (``set_job_status(..., "error")``); the workers never run a closed work.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DceAnalysis, Job, MemoirSection
from app.services import dce_analysis as analysis_svc
from app.services import dce_retrieval as retrieval
from app.services import memoir_drafting as drafting
from app.services import profile_prefill as prefill
from app.workers.queue import JobQueue


def sweep_stale_works(db: Session, queue: JobQueue, now: datetime | None = None) -> int:
    """Close every dead work of every company (unscoped session); returns how many."""
    now = now or datetime.now(UTC)
    analyses = db.scalars(
        select(DceAnalysis).where(
            DceAnalysis.status.in_(("pending", "processing")),
            DceAnalysis.updated_at < now - analysis_svc.STALE_AFTER,
        )
    ).all()
    for analysis in analyses:
        analysis_svc.close_stale(db, analysis)
    sections = db.scalars(
        select(MemoirSection).where(
            MemoirSection.status.in_(("pending", "generating")),
            MemoirSection.updated_at < now - drafting.SECTION_STALE_AFTER,
        )
    ).all()
    for section in sections:
        drafting.close_stale_section(db, section)
    readings = db.scalars(
        select(Job).where(
            Job.kind == prefill.JOB_KIND,
            Job.status.in_(("pending", "running")),
            func.coalesce(Job.started_at, Job.created_at) < now - prefill.STALE,
        )
    ).all()
    for job in readings:
        if job.ref_id is None:
            continue
        latest = prefill.latest_job(db, job.ref_id)
        if latest is not None and latest.id == job.id:
            prefill.close_stale(db, job.ref_id)
        else:  # an older one, forgotten under a newer reading: no charge of its own to find
            job.status, job.error, job.finished_at = "error", prefill.INTERRUPTED, now
    fetches = retrieval.close_stale(db, now)  # a DCE retrieval left « en cours »
    db.commit()
    for memoir_id in {s.memoir_id for s in sections}:
        drafting.maybe_finish(db, memoir_id, queue)  # the memoir may have nothing left to draft
    return len(analyses) + len(sections) + len(readings) + fetches
