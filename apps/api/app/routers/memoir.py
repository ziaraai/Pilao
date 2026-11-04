import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.ai.embeddings import Embedder, get_embedder
from app.core.deps import CurrentAuth, ScopedDb
from app.core.errors import ApiError
from app.db.models import Bid, CompanyReference, Memoir, MemoirSection, Requirement
from app.schemas.memoir import MemoirOut, OutlineIn, ReferenceChoiceOut, ReferencesIn, SectionOut
from app.services import memoir as svc

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
