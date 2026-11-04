"""RQ entry points. Run a worker with:  ``uv run rq worker -u $REDIS_URL``."""

import uuid

from app.ai.embeddings import get_embedder
from app.db.session import get_sessionmaker
from app.documents.ocr import get_ocr_engine
from app.services.dce import run_process_dce
from app.services.dce_analysis import run_analyze_dce
from app.services.document_reading import get_document_reader
from app.services.knowledge import run_index_document
from app.services.memoir_drafting import run_conformity, run_draft_section
from app.services.vault import run_read_document
from app.storage.antivirus import get_scanner
from app.storage.objects import get_storage
from app.workers.queue import get_job_queue


def index_document_job(doc_id: str) -> None:
    with get_sessionmaker()() as db:
        run_index_document(db, uuid.UUID(doc_id), get_storage(), get_embedder())


def read_compliance_document_job(doc_id: str) -> None:
    with get_sessionmaker()() as db:
        run_read_document(db, uuid.UUID(doc_id), get_storage(), get_document_reader())


def process_dce_job(version_id: str) -> None:
    with get_sessionmaker()() as db:
        run_process_dce(
            db,
            uuid.UUID(version_id),
            get_storage(),
            get_scanner(),
            get_ocr_engine(),
            queue=get_job_queue(),
        )


def analyze_dce_job(analysis_id: str) -> None:
    with get_sessionmaker()() as db:
        run_analyze_dce(db, uuid.UUID(analysis_id))


def draft_section_job(section_id: str) -> None:
    with get_sessionmaker()() as db:
        run_draft_section(db, uuid.UUID(section_id), get_embedder(), get_job_queue())


def conformity_job(memoir_id: str) -> None:
    with get_sessionmaker()() as db:
        run_conformity(db, uuid.UUID(memoir_id))
