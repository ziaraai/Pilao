"""RQ entry points. Run a worker with:  ``uv run rq worker -u $REDIS_URL``."""

import uuid

from app.ai.embeddings import get_embedder
from app.db.session import get_sessionmaker
from app.services.document_reading import get_document_reader
from app.services.knowledge import run_index_document
from app.services.vault import run_read_document
from app.storage.objects import get_storage


def index_document_job(doc_id: str) -> None:
    with get_sessionmaker()() as db:
        run_index_document(db, uuid.UUID(doc_id), get_storage(), get_embedder())


def read_compliance_document_job(doc_id: str) -> None:
    with get_sessionmaker()() as db:
        run_read_document(db, uuid.UUID(doc_id), get_storage(), get_document_reader())
