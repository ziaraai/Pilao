"""RQ entry points. Run a worker with:  ``uv run rq worker --with-scheduler -u $REDIS_URL``."""

import uuid
from datetime import UTC, datetime
from typing import cast

from app.ai.embeddings import get_embedder
from app.core.email import get_mailer
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.documents.ocr import get_ocr_engine
from app.exports.pdf import get_pdf_converter
from app.integrations.atexo import get_robot
from app.services.alerts import run_daily
from app.services.dce import run_process_dce
from app.services.dce_analysis import run_analyze_dce
from app.services.dce_retrieval import run_fetch, watch_dces
from app.services.document_reading import get_document_reader
from app.services.exports import run_export
from app.services.knowledge import run_index_document
from app.services.memoir_drafting import run_conformity, run_draft_section
from app.services.org_data import run_org_export
from app.services.profile_prefill import run_profile_prefill
from app.services.stale_works import sweep_stale_works
from app.services.tender_import import ALL_READERS, Source, run_import
from app.services.tender_import import run_all as import_tenders
from app.services.tenders import match_tenders, rematch_org, score_org
from app.services.vault import run_read_document
from app.storage.antivirus import get_scanner
from app.storage.objects import get_storage
from app.workers.host_gate import get_host_gate
from app.workers.queue import get_job_queue

configure_logging()


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
            mailer=get_mailer(),
        )


def watch_dces_job() -> None:
    """Every morning: the DCE retrieved by the robot (spec « Récupération des DCE », § 4.3)."""
    with get_sessionmaker()() as db:
        watch_dces(
            db, get_robot(), get_job_queue(), get_mailer(), get_host_gate(), datetime.now(UTC)
        )


def fetch_dce_job(fetch_id: str) -> None:
    with get_sessionmaker()() as db:
        run_fetch(
            db,
            uuid.UUID(fetch_id),
            get_robot(),
            get_storage(),
            get_scanner(),
            get_job_queue(),
            get_host_gate(),
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


def export_job(document_id: str) -> None:
    with get_sessionmaker()() as db:
        run_export(db, uuid.UUID(document_id), get_storage(), get_pdf_converter())


def match_tenders_job(tender_ids: list[str]) -> None:
    with get_sessionmaker()() as db:  # unscoped: notices are matched for every company
        match_tenders(db, [uuid.UUID(i) for i in tender_ids], get_job_queue())


def rematch_org_job(org_id: str) -> None:
    with get_sessionmaker()() as db:
        rematch_org(db, uuid.UUID(org_id), get_job_queue())


def score_tenders_job(org_id: str) -> None:
    with get_sessionmaker()() as db:
        score_org(db, uuid.UUID(org_id), get_job_queue())


def import_tenders_job() -> None:
    """Every 2 hours (P3-01, P3-02): the enabled sources, since their last pass."""
    with get_sessionmaker()() as db:  # unscoped: notices are global
        import_tenders(db, get_mailer(), get_job_queue())


def daily_alerts_job() -> None:
    with get_sessionmaker()() as db:  # unscoped: every company
        run_daily(db, get_mailer(), storage=get_storage())


def org_export_job(request_id: str) -> None:
    with get_sessionmaker()() as db:
        run_org_export(db, uuid.UUID(request_id), get_storage())


def profile_prefill_job(org_id: str) -> None:
    with get_sessionmaker()() as db:
        run_profile_prefill(db, uuid.UUID(org_id), get_storage())


def sweep_stale_works_job() -> None:
    """Every 15 minutes (lot 4): the works left for dead give their credits back."""
    with get_sessionmaker()() as db:  # unscoped: every company
        sweep_stale_works(db, get_job_queue())


def import_source_job(source: str) -> None:
    """« Importer maintenant » (lot 5): one source, since its last pass."""
    with get_sessionmaker()() as db:  # unscoped: notices are global
        run_import(db, cast(Source, source), ALL_READERS[source](), get_mailer(), get_job_queue())
