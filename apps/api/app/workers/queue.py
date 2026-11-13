"""Background job queue (RQ on Redis). API code only sees the ``JobQueue`` interface."""

import uuid
from datetime import timedelta
from functools import lru_cache
from typing import Any, Protocol

from redis import Redis
from rq import Queue, Retry, get_current_job

from app.core.config import get_settings

DCE_JOB_TIMEOUT_SECONDS = 1800  # 300-page DCE with OCR (US-3.2 CA8 targets 5 min for analysis)
ANALYSIS_JOB_TIMEOUT_SECONDS = 1800
DRAFT_JOB_TIMEOUT_SECONDS = 900
INDEX_JOB_TIMEOUT_SECONDS = 900
TENDER_JOB_TIMEOUT_SECONDS = 1800
PREFILL_JOB_TIMEOUT_SECONDS = 900
FETCH_JOB_TIMEOUT_SECONDS = 600  # the DCE robot: a few pages and a ZIP of up to 250 Mo


class JobQueue(Protocol):
    def enqueue_index_document(self, doc_id: uuid.UUID) -> None: ...
    def enqueue_read_compliance_document(self, doc_id: uuid.UUID) -> None: ...
    def enqueue_process_dce(self, version_id: uuid.UUID) -> None: ...
    def enqueue_analyze_dce(self, analysis_id: uuid.UUID) -> None: ...
    def enqueue_draft_section(self, section_id: uuid.UUID) -> None: ...
    def enqueue_conformity(self, memoir_id: uuid.UUID) -> None: ...
    def enqueue_export(self, document_id: uuid.UUID) -> None: ...
    def enqueue_match_tenders(self, tender_ids: list[uuid.UUID]) -> None: ...
    def enqueue_rematch_org(self, org_id: uuid.UUID) -> None: ...
    def enqueue_score_tenders(self, org_id: uuid.UUID) -> None: ...
    def enqueue_org_export(self, request_id: uuid.UUID) -> None: ...
    def enqueue_profile_prefill(self, org_id: uuid.UUID) -> None: ...
    def enqueue_import_source(self, source: str) -> None: ...
    def enqueue_fetch_dce(self, fetch_id: uuid.UUID, delay_seconds: int = 0) -> None: ...


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

    def enqueue_export(self, document_id: uuid.UUID) -> None:
        self._q.enqueue(
            "app.workers.jobs.export_job",
            str(document_id),
            job_timeout=DRAFT_JOB_TIMEOUT_SECONDS,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=2, interval=[30, 120]),
        )

    def enqueue_match_tenders(self, tender_ids: list[uuid.UUID]) -> None:
        self._q.enqueue(
            "app.workers.jobs.match_tenders_job",
            [str(i) for i in tender_ids],
            job_timeout=TENDER_JOB_TIMEOUT_SECONDS,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=2, interval=[60, 300]),
        )

    def enqueue_rematch_org(self, org_id: uuid.UUID) -> None:
        self._q.enqueue(
            "app.workers.jobs.rematch_org_job",
            str(org_id),
            job_timeout=TENDER_JOB_TIMEOUT_SECONDS,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=2, interval=[60, 300]),
        )

    def enqueue_score_tenders(self, org_id: uuid.UUID) -> None:
        # Jobs of one company may overlap: each match is claimed before it is scored.
        self._q.enqueue(
            "app.workers.jobs.score_tenders_job",
            str(org_id),
            job_timeout=TENDER_JOB_TIMEOUT_SECONDS,
            result_ttl=0,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=2, interval=[60, 300]),
        )

    def enqueue_org_export(self, request_id: uuid.UUID) -> None:
        self._q.enqueue(
            "app.workers.jobs.org_export_job",
            str(request_id),
            job_timeout=TENDER_JOB_TIMEOUT_SECONDS,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=2, interval=[60, 300]),
        )

    def enqueue_profile_prefill(self, org_id: uuid.UUID) -> None:
        # One model call per document of the knowledge base (US-1.6).
        self._q.enqueue(
            "app.workers.jobs.profile_prefill_job",
            str(org_id),
            job_timeout=PREFILL_JOB_TIMEOUT_SECONDS,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
            retry=Retry(max=1, interval=[120]),
        )

    def enqueue_import_source(self, source: str) -> None:
        # « Importer maintenant » from the administration (lot 5): one source, now
        self._q.enqueue(
            "app.workers.jobs.import_source_job",
            source,
            job_timeout=TENDER_JOB_TIMEOUT_SECONDS,
            result_ttl=3600,
            failure_ttl=7 * 24 * 3600,
        )

    def enqueue_fetch_dce(self, fetch_id: uuid.UUID, delay_seconds: int = 0) -> None:
        # The DCE robot (spec « Récupération des DCE »): later when its site is busy
        options: dict[str, Any] = {
            "job_timeout": FETCH_JOB_TIMEOUT_SECONDS,
            "result_ttl": 3600,
            "failure_ttl": 7 * 24 * 3600,
            "retry": Retry(max=2, interval=[60, 300]),
        }
        if delay_seconds > 0:
            self._q.enqueue_in(
                timedelta(seconds=delay_seconds),
                "app.workers.jobs.fetch_dce_job",
                str(fetch_id),
                **options,
            )
        else:
            self._q.enqueue("app.workers.jobs.fetch_dce_job", str(fetch_id), **options)


@lru_cache
def get_job_queue() -> JobQueue:
    return RqJobQueue(Queue("default", connection=Redis.from_url(get_settings().redis_url)))


def will_retry() -> bool:
    """Inside an RQ job: whether RQ runs it again if this attempt fails (``Retry`` left).
    Outside RQ (tests, commands), never."""
    job = get_current_job()
    return bool(job is not None and job.retries_left)
