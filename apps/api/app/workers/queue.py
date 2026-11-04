"""Background job queue (RQ on Redis). API code only sees the ``JobQueue`` interface."""

import uuid
from functools import lru_cache
from typing import Protocol

from redis import Redis
from rq import Queue, Retry

from app.core.config import get_settings

DCE_JOB_TIMEOUT_SECONDS = 1800  # 300-page DCE with OCR (US-3.2 CA8 targets 5 min for analysis)
ANALYSIS_JOB_TIMEOUT_SECONDS = 1800
DRAFT_JOB_TIMEOUT_SECONDS = 900
INDEX_JOB_TIMEOUT_SECONDS = 900


class JobQueue(Protocol):
    def enqueue_index_document(self, doc_id: uuid.UUID) -> None: ...
    def enqueue_read_compliance_document(self, doc_id: uuid.UUID) -> None: ...
    def enqueue_process_dce(self, version_id: uuid.UUID) -> None: ...
    def enqueue_analyze_dce(self, analysis_id: uuid.UUID) -> None: ...
    def enqueue_draft_section(self, section_id: uuid.UUID) -> None: ...
    def enqueue_conformity(self, memoir_id: uuid.UUID) -> None: ...


class RqJobQueue:
    def __init__(self, queue: Queue) -> None:
        self._q = queue

    def enqueue_index_document(self, doc_id: uuid.UUID) -> None:
        self._q.enqueue(
            "app.workers.jobs.index_document_job",
            str(doc_id),
            job_timeout=INDEX_JOB_TIMEOUT_SECONDS,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=2, interval=[30, 120]),
        )

    def enqueue_read_compliance_document(self, doc_id: uuid.UUID) -> None:
        self._q.enqueue(
            "app.workers.jobs.read_compliance_document_job",
            str(doc_id),
            job_timeout=300,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=2, interval=[30, 120]),
        )

    def enqueue_process_dce(self, version_id: uuid.UUID) -> None:
        self._q.enqueue(
            "app.workers.jobs.process_dce_job",
            str(version_id),
            job_timeout=DCE_JOB_TIMEOUT_SECONDS,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=2, interval=[30, 120]),
        )

    def enqueue_analyze_dce(self, analysis_id: uuid.UUID) -> None:
        self._q.enqueue(
            "app.workers.jobs.analyze_dce_job",
            str(analysis_id),
            job_timeout=ANALYSIS_JOB_TIMEOUT_SECONDS,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=2, interval=[60, 300]),
        )

    def enqueue_draft_section(self, section_id: uuid.UUID) -> None:
        # One job per chapter: several workers draft a memoir in parallel (US-4.2 CA1).
        self._q.enqueue(
            "app.workers.jobs.draft_section_job",
            str(section_id),
            job_timeout=DRAFT_JOB_TIMEOUT_SECONDS,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=2, interval=[60, 300]),
        )

    def enqueue_conformity(self, memoir_id: uuid.UUID) -> None:
        self._q.enqueue(
            "app.workers.jobs.conformity_job",
            str(memoir_id),
            job_timeout=DRAFT_JOB_TIMEOUT_SECONDS,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=2, interval=[60, 300]),
        )


@lru_cache
def get_job_queue() -> JobQueue:
    return RqJobQueue(Queue("default", connection=Redis.from_url(get_settings().redis_url)))
