"""Technical memoir: outline and references (P2-01 / P2-02). Drafting comes with P2-03."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.embeddings import Embedder
from app.core.errors import ApiError
from app.db.models import (
    AuditLog,
    Bid,
    CompanyReference,
    DceAnalysis,
    DocumentChunk,
    KnowledgeDocument,
    Memoir,
    MemoirSection,
    Requirement,
    User,
)
from app.domain import imposed_font
from app.domain import memoir_plan as plan
from app.schemas.memoir import OutlineIn
from app.services.references_selection import auto_selection, select_references


def latest_ready_analysis(db: Session, bid: Bid) -> DceAnalysis:
    analysis = db.scalars(
        select(DceAnalysis)
        .where(DceAnalysis.bid_id == bid.id, DceAnalysis.status == "ready")
        .order_by(DceAnalysis.created_at.desc())
    ).first()
    if analysis is None or analysis.data is None:
        raise ApiError(
            409,
            "no_analysis",
            "Le mémoire s'appuie sur l'analyse du DCE : attendez qu'elle soit prête.",
        )
    return analysis


def template_headings(db: Session) -> list[str]:
    """Chapter titles of the most recent ready "memoir template" of the company."""
    template = db.scalars(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.kind == "memoir_template", KnowledgeDocument.status == "ready")
        .order_by(KnowledgeDocument.created_at.desc())
    ).first()
    if template is None:
        return []
    headings = db.scalars(
        select(DocumentChunk.heading)
        .where(DocumentChunk.source_type == "knowledge", DocumentChunk.source_id == template.id)
        .order_by(DocumentChunk.position)
    )
    return plan.template_outline([h for h in headings if h])


def create_memoir(db: Session, user: User, bid: Bid, embedder: Embedder) -> Memoir:
    analysis = latest_ready_analysis(db, bid)
    data: dict[str, Any] = analysis.data or {}
    memoir_req = data.get("memoir_requirements") or {}
    criteria = plan.flatten_criteria(data.get("award_criteria") or [])
    source, sections = plan.build_outline(
        list(memoir_req.get("imposed_outline") or []), template_headings(db), criteria
    )
    requirements = db.scalars(
        select(Requirement)
        .where(Requirement.dce_analysis_id == analysis.id)
        .order_by(Requirement.position)
    ).all()
    plan.assign_requirements(sections, [(r.ref, r.category, r.text) for r in requirements])
    font = imposed_font.from_analysis(data)
    total = plan.assign_word_budgets(
        sections, memoir_req.get("max_pages"), font.size if font else None
    )

    title = ((data.get("key_info") or {}).get("title") or {}) or {}
    tender_text = " ".join([str(title.get("value") or bid.title), *(r.text for r in requirements)])
    amount = ((data.get("key_info") or {}).get("estimated_amount_eur_ht") or {}).get("value")
    picks, _warning = select_references(
        db,
        bid.org_id,
        embedder,
        tender_text,
        round(amount * 100) if isinstance(amount, int | float) else None,
    )

    number = (db.scalar(select(func.max(Memoir.version)).where(Memoir.bid_id == bid.id)) or 0) + 1
    memoir = Memoir(
        id=uuid.uuid4(),
        bid_id=bid.id,
        dce_analysis_id=analysis.id,
        version=number,
        status="draft",
        outline_source=source,
        max_pages=memoir_req.get("max_pages"),
        word_budget=total,
        reference_ids=[uuid.UUID(p.reference_id) for p in auto_selection(picks)],
        reference_scores=[
            {"id": p.reference_id, "score": p.score, "reasons": p.reasons} for p in picks
        ],
        created_by=user.id,
    )
    db.add(memoir)
    for position, s in enumerate(sections):
        db.add(
            MemoirSection(
                memoir_id=memoir.id,
                position=position,
                title=s.title,
                criterion_ref=s.criterion,
                criterion_weight=s.weight,
                requirement_refs=s.requirement_refs,
                word_budget=s.word_budget,
            )
        )
    db.add(
        AuditLog(
            user_id=user.id,
            action="create",
            entity="memoir",
            entity_id=memoir.id,
            meta={"version": number, "outline_source": source},
        )
    )
    try:
        db.commit()
    except IntegrityError:  # two "prepare" clicks at once
        db.rollback()
        raise ApiError(
            409, "memoir_exists", "Ce mémoire vient d'être créé : rechargez la page."
        ) from None
    return memoir


def _editable(memoir: Memoir) -> None:
    if memoir.status != "draft":
        raise ApiError(
            409,
            "memoir_locked",
            "La rédaction a commencé : créez une nouvelle version pour changer le plan.",
        )


def update_outline(db: Session, user: User, memoir: Memoir, data: OutlineIn) -> None:
    """US-4.1 CA4: the user edits the outline before drafting (titles, order, requirements)."""
    _editable(memoir)
    known = set(
        db.scalars(
            select(Requirement.ref).where(Requirement.dce_analysis_id == memoir.dce_analysis_id)
        )
    )
    unknown = sorted({ref for s in data.sections for ref in s.requirement_refs} - known)
    if unknown:
        raise ApiError(422, "unknown_requirement", f"Exigences inconnues : {', '.join(unknown)}.")
    existing = {
        s.id: s
        for s in db.scalars(select(MemoirSection).where(MemoirSection.memoir_id == memoir.id))
    }
    kept: set[uuid.UUID] = set()
    for position, item in enumerate(data.sections):
        section = existing.get(item.id) if item.id else None
        if section is None:
            section = MemoirSection(memoir_id=memoir.id)
            db.add(section)
        else:
            kept.add(section.id)
        section.position, section.title = position, item.title
        section.requirement_refs = list(dict.fromkeys(item.requirement_refs))
        section.word_budget = item.word_budget
    for section_id, section in existing.items():
        if section_id not in kept:
            db.delete(section)
    memoir.word_budget = sum(s.word_budget for s in data.sections)
    db.add(AuditLog(user_id=user.id, action="update_outline", entity="memoir", entity_id=memoir.id))
    db.commit()


def update_references(
    db: Session, user: User, memoir: Memoir, reference_ids: list[uuid.UUID]
) -> None:
    _editable(memoir)
    owned = set(
        db.scalars(select(CompanyReference.id).where(CompanyReference.id.in_(reference_ids)))
    )
    if owned != set(reference_ids):
        raise ApiError(422, "unknown_reference", "Référence introuvable.")
    memoir.reference_ids = list(dict.fromkeys(reference_ids))
    db.add(
        AuditLog(user_id=user.id, action="update_references", entity="memoir", entity_id=memoir.id)
    )
    db.commit()
