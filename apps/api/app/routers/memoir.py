import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.ai.embeddings import Embedder, get_embedder
from app.core.deps import CurrentAuth, ScopedDb
from app.core.errors import ApiError
from app.db.models import (
    Bid,
    CompanyReference,
    ConformityItem,
    DceFile,
    Memoir,
    MemoirSection,
    Requirement,
)
from app.domain.memoir_checks import count_words
from app.domain.memoir_plan import WORDS_PER_PAGE
from app.schemas.memoir import (
    ConformityItemOut,
    ConformityOut,
    MemoirOut,
    OutlineIn,
    ReferenceChoiceOut,
    ReferencesIn,
    RegenerateIn,
    SectionOut,
    SourceRef,
)
from app.services import memoir as svc
from app.services import memoir_drafting as drafting
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(tags=["memoir"])


def _bid(db: ScopedDb, bid_id: uuid.UUID) -> Bid:
    bid = db.get(Bid, bid_id)
    if bid is None:
        raise ApiError(404, "not_found", "Dossier introuvable.")
    return bid


def _memoir(db: ScopedDb, memoir_id: uuid.UUID) -> Memoir:
    memoir = db.get(Memoir, memoir_id)
    if memoir is None:
        raise ApiError(404, "not_found", "Mémoire introuvable.")
    return memoir


def memoir_out(db: ScopedDb, memoir: Memoir) -> MemoirOut:
    sections = db.scalars(
        select(MemoirSection)
        .where(MemoirSection.memoir_id == memoir.id)
        .order_by(MemoirSection.position)
    ).all()
    scores = {s["id"]: s for s in memoir.reference_scores}
    selected = {str(r) for r in memoir.reference_ids}
    ids = [uuid.UUID(i) for i in dict.fromkeys([*scores, *selected])]
    refs = {
        str(r.id): r
        for r in db.scalars(select(CompanyReference).where(CompanyReference.id.in_(ids)))
    }
    references = [
        ReferenceChoiceOut(
            id=r.id,
            client_name=r.client_name,
            title=r.title,
            year=r.year,
            amount_cents=r.amount_cents,
            score=scores.get(rid, {}).get("score"),
            reasons=scores.get(rid, {}).get("reasons", []),
            selected=rid in selected,
        )
        for rid, r in ((rid, refs.get(rid)) for rid in map(str, ids))
        if r is not None  # a reference deleted since then simply disappears
    ]
    all_refs = list(
        db.scalars(
            select(Requirement.ref)
            .where(Requirement.dce_analysis_id == memoir.dce_analysis_id)
            .order_by(Requirement.position)
        )
    )
    assigned = {ref for s in sections for ref in s.requirement_refs}
    words = sum(count_words(s.content_md or "") for s in sections)
    pages = math.ceil(words / WORDS_PER_PAGE) if words else None
    warning = None
    if pages and memoir.max_pages and pages > memoir.max_pages:
        warning = (
            f"Environ {pages} pages pour {memoir.max_pages} autorisées par le règlement : "
            "raccourcissez certains chapitres."
        )
    return MemoirOut(
        id=memoir.id,
        version=memoir.version,
        status=memoir.status,
        outline_source=memoir.outline_source,
        max_pages=memoir.max_pages,
        word_budget=memoir.word_budget,
        sections=[SectionOut.model_validate(s, from_attributes=True) for s in sections],
        references=references,
        unassigned_requirements=[r for r in all_refs if r not in assigned],
        conformity_status=memoir.conformity_status,
        conformity_error=memoir.conformity_error,
        drafted_words=words,
        estimated_pages=pages,
        page_warning=warning,
        created_at=memoir.created_at,
    )


@router.post("/bids/{bid_id}/memoir", status_code=201)
def create(
    bid_id: uuid.UUID,
    ctx: CurrentAuth,
    db: ScopedDb,
    embedder: Annotated[Embedder, Depends(get_embedder)],
) -> MemoirOut:
    """Prepare a new memoir version: outline (RC > template > sector) and references."""
    return memoir_out(db, svc.create_memoir(db, ctx.user, _bid(db, bid_id), embedder))


@router.get("/bids/{bid_id}/memoir")
def latest(bid_id: uuid.UUID, db: ScopedDb) -> MemoirOut:
    bid = _bid(db, bid_id)
    memoir = db.scalars(
        select(Memoir).where(Memoir.bid_id == bid.id).order_by(Memoir.version.desc())
    ).first()
    if memoir is None:
        raise ApiError(404, "not_found", "Aucun mémoire pour ce dossier.")
    return memoir_out(db, memoir)


@router.get("/memoirs/{memoir_id}")
def read(memoir_id: uuid.UUID, db: ScopedDb) -> MemoirOut:
    return memoir_out(db, _memoir(db, memoir_id))


@router.put("/memoirs/{memoir_id}/outline")
def put_outline(memoir_id: uuid.UUID, data: OutlineIn, ctx: CurrentAuth, db: ScopedDb) -> MemoirOut:
    memoir = _memoir(db, memoir_id)
    svc.update_outline(db, ctx.user, memoir, data)
    return memoir_out(db, memoir)


@router.put("/memoirs/{memoir_id}/references")
def put_references(
    memoir_id: uuid.UUID, data: ReferencesIn, ctx: CurrentAuth, db: ScopedDb
) -> MemoirOut:
    memoir = _memoir(db, memoir_id)
    svc.update_references(db, ctx.user, memoir, data.reference_ids)
    return memoir_out(db, memoir)


Queue = Annotated[JobQueue, Depends(get_job_queue)]


@router.post("/memoirs/{memoir_id}/generate", status_code=202)
def generate(memoir_id: uuid.UUID, ctx: CurrentAuth, db: ScopedDb, queue: Queue) -> MemoirOut:
    """US-4.2: one job per chapter (drafted in parallel), then the conformity matrix."""
    memoir = _memoir(db, memoir_id)
    drafting.start_generation(db, ctx.user, memoir, queue)
    return memoir_out(db, memoir)


@router.post("/memoir-sections/{section_id}/regenerate", status_code=202)
def regenerate(
    section_id: uuid.UUID, data: RegenerateIn, ctx: CurrentAuth, db: ScopedDb, queue: Queue
) -> MemoirOut:
    """US-4.4 CA2: new version of one chapter, with a free instruction."""
    section = db.get(MemoirSection, section_id)
    if section is None:
        raise ApiError(404, "not_found", "Chapitre introuvable.")
    drafting.regenerate_section(
        db, ctx.user, section, data.instruction, data.add_requirement_refs, queue
    )
    return memoir_out(db, db.get_one(Memoir, section.memoir_id))


_ORDER = {"missing": 0, "partial": 1, "covered": 2}


@router.get("/memoirs/{memoir_id}/conformity")
def conformity(memoir_id: uuid.UUID, db: ScopedDb) -> ConformityOut:
    memoir = _memoir(db, memoir_id)
    sections = db.scalars(select(MemoirSection).where(MemoirSection.memoir_id == memoir.id)).all()
    titles = {s.id: s.title for s in sections}
    outline_home = {ref: s.id for s in sections for ref in s.requirement_refs}
    files = {
        file_id: path
        for file_id, path in db.execute(
            select(DceFile.id, DceFile.path)
            .join(Requirement, Requirement.source_file_id == DceFile.id)
            .where(Requirement.dce_analysis_id == memoir.dce_analysis_id)
        )
    }
    rows = db.execute(
        select(ConformityItem, Requirement)
        .join(Requirement, Requirement.id == ConformityItem.requirement_id)
        .where(ConformityItem.memoir_id == memoir.id)
        .order_by(Requirement.position)
    ).all()
    items = [
        ConformityItemOut(
            requirement_ref=r.ref,
            requirement_text=r.text,
            importance=r.importance,
            source=(
                SourceRef(file=files[r.source_file_id], page=r.page, dce_file_id=r.source_file_id)
                if r.source_file_id in files
                else None
            ),
            status=item.status,
            method=item.method,
            excerpt=item.excerpt,
            comment=item.comment,
            section_id=item.section_id,
            section_title=titles.get(item.section_id) if item.section_id else None,
            target_section_id=item.section_id or outline_home.get(r.ref),
        )
        for item, r in rows
    ]
    items.sort(key=lambda i: _ORDER[i.status])  # stable: CCTP order within a status
    counts = {k: sum(i.status == k for i in items) for k in _ORDER}
    return ConformityOut(
        status=memoir.conformity_status,
        error=memoir.conformity_error,
        counts=counts,
        items=items,
    )


@router.post("/memoirs/{memoir_id}/conformity", status_code=202)
def rerun_conformity(memoir_id: uuid.UUID, db: ScopedDb, queue: Queue) -> ConformityOut:
    memoir = _memoir(db, memoir_id)
    drafting.request_conformity(db, memoir, queue)
    return conformity(memoir_id, db)
