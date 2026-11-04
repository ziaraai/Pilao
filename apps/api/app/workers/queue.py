"""Background job queue (RQ on Redis). API code only sees the ``JobQueue`` interface."""

import uuid
from functools import lru_cache
from typing import Protocol

from redis import Redis
from rq import Queue, Retry

from app.core.config import get_settings


class JobQueue(Protocol):
    def enqueue_index_document(self, doc_id: uuid.UUID) -> None: ...
    def enqueue_read_compliance_document(self, doc_id: uuid.UUID) -> None: ...


class RqJobQueue:
    def __init__(self, queue: Queue) -> None:
        self._q = queue

    def enqueue_index_document(self, doc_id: uuid.UUID) -> None:
        self._q.enqueue(
            "app.workers.jobs.index_document_job",
            str(doc_id),
            job_timeout=900,
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


@lru_cache
def get_job_queue() -> JobQueue:
    return RqJobQueue(Queue("default", connection=Redis.from_url(get_settings().redis_url)))
