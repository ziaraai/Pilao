"""Pre-filling the profile from the company's own documents (US-1.6, spec 2026-11-09).

A background job reads every indexed document of the knowledge base, asks the model for the
staff, equipment, certifications and references written in it, checks each line against the
document (app/domain/profile_prefill.py) and stores what is left as proposals. Nothing joins
the profile until the user accepts it.
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai import llm
from app.ai.prompts import load_prompt
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    Certification,
    CompanyReference,
    Equipment,
    File,
    HumanResource,
    Job,
    KnowledgeDocument,
    Organization,
    ProfileSuggestion,
)
from app.documents.extract import Block, ExtractionError
from app.domain.dce import normalize
from app.domain.profile_prefill import (
    KINDS,
    Clean,
    Located,
    Passage,
    clean,
    dedupe,
    key_of,
    locate,
)
from app.schemas.profile_prefill import (
    ProfileExtraction,
    ReadJobOut,
    SuggestionOut,
    SuggestionsOut,
)
from app.services.jobs import set_job_status
from app.services.knowledge import document_blocks
from app.storage.objects import ObjectStorage
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.profile_prefill")

PROMPT = "extraction_profil"
TASK = "profile_extraction"
MAX_CHARS = 60_000  # above this, only the passages about means and references are sent
MAX_OUTPUT_TOKENS = 8_000
JOB_KIND = "profile_prefill"
STALE = timedelta(minutes=30)  # a reading older than this no longer blocks a new one
EMPTY_NOTE = "{title} : aucun passage sur vos moyens ou vos références."
FAILED_NOTE = "{title} : lecture impossible, réessayez plus tard."
TOPICS = (
    "moyen",
    "personnel",
    "effectif",
    "equipe",
    "materiel",
    "equipement",
    "machine",
    "client",
    "reference",
    "chantier",
    "certif",
    "qualif",
    "label",
)


def blocks_to_passages(blocks: list[Block]) -> list[Passage]:
    """One passage per block. A heading is a passage too: short lines of a memoir (an
    organigram, a list of machines) are often taken for headings."""
    passages: list[Passage] = []
    heading: str | None = None
    for block in blocks:
        if block.kind == "heading":
            heading = block.text
        passages.append(Passage(block.text, block.page, heading))
    return passages


def document_passages(db: Session, doc: KnowledgeDocument, storage: ObjectStorage) -> list[Passage]:
    """The document read again from its file, every line kept with its page (the indexed
    chunks drop a heading whose section is empty)."""
    record = db.get_one(File, doc.file_id)
    fileobj = storage.get(record.storage_key)
    try:
        return blocks_to_passages(document_blocks(fileobj, record.mime))
    finally:
        fileobj.close()


def _neutralize(text: str) -> str:
    """A document must not be able to close its own tag (prompt injection)."""
    return text.replace("<profile_document", "‹profile_document").replace(
        "</profile_document", "‹/profile_document"
    )


def render_passages(passages: list[Passage]) -> str:
    """The text sent to the model: ``[p. N]`` when the page changes, ``## heading`` when the
    part changes, then the passage."""
    lines: list[str] = []
    page: int | None = None
    heading: str | None = None
    for p in passages:
        if p.page is not None and p.page != page:
            lines.append(f"[p. {p.page}]")
            page = p.page
        if p.heading and p.heading != heading:
            lines.append(f"## {_neutralize(p.heading)}")
            heading = p.heading
            if p.content == p.heading:  # the heading's own passage: already written
                continue
        lines.append(_neutralize(p.content))
    return "\n".join(lines)


def select_passages(passages: list[Passage], max_chars: int = MAX_CHARS) -> list[Passage]:
    """Everything if it fits; otherwise the passages about staff, equipment, clients,
    references or certifications, in the document's order, up to ``max_chars``."""
    if len(render_passages(passages)) <= max_chars:
        return passages
    kept: list[Passage] = []
    size = 0
    for p in passages:
        if not any(t in normalize(f"{p.heading or ''} {p.content}") for t in TOPICS):
            continue
        cost = len(render_passages([p])) + 1  # an upper bound: page and heading marks repeat
        if size + cost > max_chars:
            break
        kept.append(p)
        size += cost
    return kept


def latest_job(db: Session, org_id: uuid.UUID) -> Job | None:
    return db.scalars(
        select(Job)
        .where(Job.kind == JOB_KIND, Job.ref_id == org_id)
        .order_by(Job.created_at.desc())
        .limit(1)
    ).first()


def _ready_documents(db: Session) -> list[KnowledgeDocument]:
    return list(
        db.scalars(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.status == "ready")
            .order_by(KnowledgeDocument.created_at)
        )
    )


def request_read(db: Session, org: Organization, queue: JobQueue) -> Job:
    """Start a reading of the knowledge base (one at a time per company)."""
    if not _ready_documents(db):
        raise ApiError(
            409, "no_documents", "Déposez d'abord un document dans la base documentaire."
        )
    last = latest_job(db, org.id)
    if (
        last is not None
        and last.status in ("pending", "running")
        and last.created_at > datetime.now(UTC) - STALE
    ):
        raise ApiError(409, "already_running", "Une lecture est déjà en cours.")
    job = Job(kind=JOB_KIND, ref_id=org.id, org_id=org.id, status="pending")
    db.add(job)
    db.commit()
    try:
        queue.enqueue_profile_prefill(org.id)
    except Exception:
        logger.exception("could not enqueue the profile pre-fill of %s", org.id)
        job.status, job.error = "error", "File d'attente indisponible. Relancez la lecture."
        db.commit()
    return job


def _known_keys(db: Session) -> dict[str, set[str]]:
    """Keys of what the profile already has and of the proposals already decided."""
    known: dict[str, set[str]] = {k: set() for k in KINDS}
    for (q,) in db.execute(select(HumanResource.qualification)):
        known["human_resource"].add(key_of("human_resource", {"qualification": q}))
    for (name,) in db.execute(select(Equipment.name)):
        known["equipment"].add(key_of("equipment", {"name": name}))
    for (name,) in db.execute(select(Certification.name)):
        known["certification"].add(key_of("certification", {"name": name}))
    for client, title in db.execute(select(CompanyReference.client_name, CompanyReference.title)):
        known["reference"].add(key_of("reference", {"client_name": client, "title": title}))
    for kind, key in db.execute(
        select(ProfileSuggestion.kind, ProfileSuggestion.key).where(
            ProfileSuggestion.status != "pending"
        )
    ):
        known[kind].add(key)
    return known


def _answer_lines(data: ProfileExtraction) -> list[tuple[str, dict[str, Any], str]]:
    groups = (
        ("human_resource", data.human_resources),
        ("equipment", data.equipment),
        ("certification", data.certifications),
        ("reference", data.references),
    )
    return [
        (kind, item.model_dump(exclude={"excerpt"}), item.excerpt)
        for kind, items in groups
        for item in items
    ]


def _title(doc: KnowledgeDocument) -> str:
    return doc.title.replace('"', "'")


def _read_document(
    db: Session,
    org: Organization,
    doc: KnowledgeDocument,
    known: dict[str, set[str]],
    storage: ObjectStorage,
) -> tuple[list[ProfileSuggestion], str | None]:
    """The proposals found in one document, and a note when it gives none."""
    try:
        passages = select_passages(document_passages(db, doc, storage))
    except ExtractionError:
        return [], FAILED_NOTE.format(title=doc.title)
    if not passages:
        return [], EMPTY_NOTE.format(title=doc.title)
    prompt = load_prompt(PROMPT)
    system, user = prompt.render(
        company_name=org.name,
        document_title=_title(doc),
        passages=render_passages(passages),
        json_schema=json.dumps(ProfileExtraction.model_json_schema(), ensure_ascii=False),
    )
    try:
        result = llm.complete(
            db,
            org_id=org.id,
            task=TASK,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_model=ProfileExtraction,
            prompt_version=prompt.version,
            max_tokens=MAX_OUTPUT_TOKENS,
        )
    except llm.LlmInvalidOutput:
        return [], FAILED_NOTE.format(title=doc.title)
    found: list[tuple[Clean, Located, str]] = []
    for kind, raw, excerpt in _answer_lines(result.data):
        where = locate(excerpt, passages)  # a sentence not in the document: rejected
        line = clean(kind, raw, excerpt) if where is not None else None
        if line is not None and where is not None:
            found.append((line, where, excerpt))
    rows: list[ProfileSuggestion] = []
    for kind in KINDS:
        of_kind = [f for f in found if f[0].kind == kind]
        for line in dedupe([f[0] for f in of_kind], known[kind]):
            where, excerpt = next((w, e) for c, w, e in of_kind if c is line)
            known[kind].add(line.key)
            rows.append(
                ProfileSuggestion(
                    org_id=org.id,
                    kind=kind,
                    data=line.data,
                    missing=line.missing,
                    document_id=doc.id,
                    page=where.page,
                    heading=where.heading,
                    excerpt=excerpt.strip()[:500],
                    key=line.key,
                )
            )
    return rows, None if rows else EMPTY_NOTE.format(title=doc.title)


def run_profile_prefill(db: Session, org_id: uuid.UUID, storage: ObjectStorage) -> None:
    """The background job: read each ready document, keep the sourced lines as proposals.
    The notes of a reading that succeeded (documents it could not use) go in ``jobs.error``."""
    scope_session(db, org_id)
    org = db.get(Organization, org_id)
    job = latest_job(db, org_id)
    if org is None or job is None:
        return
    set_job_status(db, JOB_KIND, org_id, "running")
    job.progress = 0
    db.execute(
        delete(ProfileSuggestion).where(
            ProfileSuggestion.org_id == org_id, ProfileSuggestion.status == "pending"
        )
    )
    db.commit()
    docs = _ready_documents(db)
    known = _known_keys(db)
    notes: list[str] = []
    try:
        for done, doc in enumerate(docs, start=1):
            rows, note = _read_document(db, org, doc, known, storage)
            db.add_all(rows)
            if note:
                notes.append(note)
            job.progress = round(done * 100 / len(docs))
            db.commit()
    except llm.LlmError as exc:
        db.rollback()
        set_job_status(db, JOB_KIND, org_id, "error", str(exc))
        db.commit()
        return
    set_job_status(db, JOB_KIND, org_id, "done", "\n".join(notes) or None)
    db.commit()


def job_out(job: Job) -> ReadJobOut:
    done = job.status == "done"
    return ReadJobOut(
        status=job.status,
        progress=job.progress,
        error=job.error if job.status == "error" else None,
        notes=(job.error or "").splitlines() if done else [],
        finished_at=job.finished_at,
    )


def list_suggestions(db: Session, org: Organization) -> SuggestionsOut:
    """The last reading and the proposals waiting for a decision, by kind."""
    job = latest_job(db, org.id)
    ready = db.scalar(
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(KnowledgeDocument.status == "ready")
    )
    rows = db.execute(
        select(ProfileSuggestion, KnowledgeDocument.title)
        .join(KnowledgeDocument, KnowledgeDocument.id == ProfileSuggestion.document_id)
        .where(ProfileSuggestion.status == "pending")
        .order_by(ProfileSuggestion.created_at)
    ).all()
    ordered = sorted(rows, key=lambda r: KINDS.index(r[0].kind))
    return SuggestionsOut(
        job=job_out(job) if job is not None else None,
        documents_ready=ready or 0,
        items=[
            SuggestionOut(
                id=s.id,
                kind=s.kind,
                data=s.data,
                missing=s.missing,
                document_title=title,
                page=s.page,
                heading=s.heading,
                excerpt=s.excerpt,
            )
            for s, title in ordered
        ],
    )
