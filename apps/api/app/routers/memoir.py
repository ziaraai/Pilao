import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.ai.embeddings import Embedder, get_embedder
from app.core.deps import CurrentAuth, ScopedDb, require_module
from app.core.errors import ApiError
from app.db.models import (
    Bid,
    CompanyReference,
    ConformityItem,
    DceFile,
    Memoir,
    MemoirSection,
    MemoirSectionRevision,
    Requirement,
    User,
)
from app.domain.memoir_checks import count_words
from app.schemas.memoir import (
    ConformityItemOut,
    ConformityOut,
    MemoirOut,
    MemoirVersionOut,
    OutlineIn,
    ReferenceChoiceOut,
    ReferencesIn,
    RegenerateIn,
    RestoreIn,
    RevisionOut,
    SectionEditIn,
    SectionOut,
    SourceRef,
)
from app.services import credits
from app.services import exports as exports_svc
from app.services import memoir as svc
from app.services import memoir_drafting as drafting
from app.services import memoir_editing as editing
from app.workers.queue import JobQueue, get_job_queue

router = APIRouter(tags=["memoir"], dependencies=[Depends(require_module("reponse"))])


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
    free = credits.free_relaunches(db, memoir.id, sections)  # lot 4
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
    pages = exports_svc.estimated_pages(db, memoir, words)
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
        sections=[
            SectionOut.model_validate(s, from_attributes=True).model_copy(
                update={"relaunch_free": s.id in free}
            )
            for s in sections
        ],
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


@router.get("/bids/{bid_id}/memoirs")
def versions(bid_id: uuid.UUID, db: ScopedDb) -> list[MemoirVersionOut]:
    """US-4.4 CA4: every version of the memoir of this bid, newest first."""
    bid = _bid(db, bid_id)
    memoirs = db.scalars(
        select(Memoir).where(Memoir.bid_id == bid.id).order_by(Memoir.version.desc())
    ).all()
    statuses: dict[uuid.UUID, list[str]] = {}
    for memoir_id, status in db.execute(
        select(MemoirSection.memoir_id, MemoirSection.status).where(
            MemoirSection.memoir_id.in_([m.id for m in memoirs])
        )
    ):
        statuses.setdefault(memoir_id, []).append(status)
    return [
        MemoirVersionOut(
            id=m.id,
            version=m.version,
            status=m.status,
            created_at=m.created_at,
            chapters=len(statuses.get(m.id, [])),
            drafted=sum(s == "ready" for s in statuses.get(m.id, [])),
        )
        for m in memoirs
    ]


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
    section = _section(db, section_id)
    drafting.regenerate_section(
        db, ctx.user, section, data.instruction, data.add_requirement_refs, queue
    )
    return memoir_out(db, db.get_one(Memoir, section.memoir_id))


def _section(db: ScopedDb, section_id: uuid.UUID) -> MemoirSection:
    section = db.get(MemoirSection, section_id)
    if section is None:
        raise ApiError(404, "not_found", "Chapitre introuvable.")
    return section


@router.put("/memoir-sections/{section_id}")
def edit_section(
    section_id: uuid.UUID, data: SectionEditIn, ctx: CurrentAuth, db: ScopedDb
) -> MemoirOut:
    """US-4.4 CA1: the user's text replaces the chapter (a new revision, the old one is kept)."""
    section = editing.edit_section(
        db, ctx.user, _section(db, section_id), data.body_md, data.base_revision
    )
    return memoir_out(db, db.get_one(Memoir, section.memoir_id))


@router.get("/memoir-sections/{section_id}/revisions")
def revisions(section_id: uuid.UUID, db: ScopedDb) -> list[RevisionOut]:
    section = _section(db, section_id)
    rows = db.execute(
        select(MemoirSectionRevision, User.full_name, User.email)
        .outerjoin(User, User.id == MemoirSectionRevision.created_by)
        .where(MemoirSectionRevision.section_id == section.id)
        .order_by(MemoirSectionRevision.revision.desc())
        .limit(100)
    ).all()
    return [
        RevisionOut(
            id=r.id,
            revision=r.revision,
            origin=r.origin,
            created_at=r.created_at,
            author=(name or email) if r.created_by else None,
            instruction=r.instruction,
            model=r.model,
            words=count_words(r.content_md),
            content_md=r.content_md,
        )
        for r, name, email in rows
    ]


@router.post("/memoir-sections/{section_id}/revisions/{revision_id}/restore")
def restore(
    section_id: uuid.UUID,
    revision_id: uuid.UUID,
    data: RestoreIn,
    ctx: CurrentAuth,
    db: ScopedDb,
) -> MemoirOut:
    section = editing.restore_revision(
        db, ctx.user, _section(db, section_id), revision_id, data.base_revision
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
