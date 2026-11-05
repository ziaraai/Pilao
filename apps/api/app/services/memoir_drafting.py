"""Chapter drafting (US-4.2, P2-03) and conformity matrix (US-4.3, P2-04)."""

import json
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import llm
from app.ai.embeddings import Embedder, EmbeddingError
from app.ai.prompts import load_prompt
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    AuditLog,
    Bid,
    Certification,
    CompanyProfile,
    CompanyReference,
    ConformityItem,
    DceAnalysis,
    DceFile,
    Equipment,
    HumanResource,
    Job,
    Memoir,
    MemoirSection,
    Organization,
    Requirement,
    User,
)
from app.domain.memoir_checks import check_chapter, force_title
from app.domain.trades import TRADES
from app.schemas.drafting import ChapterOut, MatrixOut
from app.services.jobs import set_job_status
from app.services.knowledge import search_chunks
from app.services.memoir_editing import add_revision
from app.workers.queue import DRAFT_JOB_TIMEOUT_SECONDS, JobQueue

logger = logging.getLogger("pilao.memoir")
JOB_SECTION = "draft_memoir_section"
JOB_CONFORMITY = "memoir_conformity"
CHAPTER_PROMPT = "generation_memoire_chapitre"
MATRIX_PROMPT = "matrice_conformite"
EXCERPTS_PER_CHAPTER = 6
# 3 attempts of at most DRAFT_JOB_TIMEOUT_SECONDS each, plus the retry intervals (60 s, 300 s)
SECTION_STALE_AFTER = timedelta(seconds=4 * DRAFT_JOB_TIMEOUT_SECONDS)


def _tag_safe(text: str) -> str:
    """Data inside our XML-like tags must not be able to close them (prompt injection)."""
    return re.sub(
        r"</?\s*(excerpt|requirements|company_data|company_excerpts|references|tender|section|memoir|previous)",
        "‹",
        text,
    )


# ---------- inputs: only the company's own, confirmed data (CLAUDE.md §5.1 / §5.3) --------


def company_data(db: Session, org: Organization) -> dict[str, Any]:
    """Structured facts in the shape of schemas/company_profile.schema.json."""
    profile = db.scalar(select(CompanyProfile))
    address = " ".join(x for x in (org.address_line, org.postal_code, org.city) if x) or None
    revenues = (
        [profile.revenue_y1_cents, profile.revenue_y2_cents, profile.revenue_y3_cents]
        if profile
        else []
    )
    return {
        "identity": {
            "name": org.name,
            "siret": org.siret,
            "legal_form": org.legal_form,
            "address": address,
        },
        "trades": [TRADES[t].label for t in (profile.trades if profile else []) if t in TRADES],
        "departments": profile.departments if profile else [],
        "revenue_last_3_years_eur": [None if r is None else r / 100 for r in revenues],
        "human_resources": [
            {"qualification": h.qualification, "count": h.count, "description": h.description}
            for h in db.scalars(select(HumanResource).order_by(HumanResource.created_at))
        ],
        "equipment": [
            {"name": e.name, "category": e.category, "quantity": e.quantity}
            for e in db.scalars(select(Equipment).order_by(Equipment.created_at))
        ],
        "certifications": [
            {"name": c.name, "valid_until": c.valid_until.isoformat() if c.valid_until else None}
            for c in db.scalars(select(Certification).order_by(Certification.created_at))
        ],
    }


def _references(db: Session, memoir: Memoir) -> list[dict[str, Any]]:
    if not memoir.reference_ids:
        return []
    refs = db.scalars(select(CompanyReference).where(CompanyReference.id.in_(memoir.reference_ids)))
    return [
        {
            "client": r.client_name,
            "client_type": "public" if r.client_type == "public" else "privé",
            "objet": r.title,
            "lieu": r.location,
            "année": r.year,
            "montant_eur_ht": None if r.amount_cents is None else r.amount_cents / 100,
            "durée_mois": r.duration_months,
            "description": r.description,
        }
        for r in refs
    ]


def _requirements(
    db: Session, memoir: Memoir, refs: list[str]
) -> list[tuple[Requirement, str | None]]:
    if not refs:
        return []
    rows = db.execute(
        select(Requirement, DceFile.path)
        .outerjoin(DceFile, DceFile.id == Requirement.source_file_id)
        .where(Requirement.dce_analysis_id == memoir.dce_analysis_id, Requirement.ref.in_(refs))
        .order_by(Requirement.position)
    ).all()
    return [(r, path) for r, path in rows]


SITE_CATEGORIES = ("surface", "schedule", "frequency")
MAX_SITE_FACTS = 25


def _cited(r: Requirement, path: str | None) -> str:
    return f"{_tag_safe(r.text)} (source : {path or 'DCE'}{f' p. {r.page}' if r.page else ''})"


def _site_facts(db: Session, memoir: Memoir, own_refs: list[str]) -> str:
    """The site's surfaces, hours and frequencies, for every chapter (never contradicted).

    Without them, a chapter on staff asked for the opening hours that the CCTP gives in a
    requirement attached to another chapter (real-model test, phase 0).
    """
    rows = db.execute(
        select(Requirement, DceFile.path)
        .outerjoin(DceFile, DceFile.id == Requirement.source_file_id)
        .where(
            Requirement.dce_analysis_id == memoir.dce_analysis_id,
            Requirement.category.in_(SITE_CATEGORIES),
            Requirement.ref.not_in(own_refs or [""]),
        )
        .order_by(Requirement.position)
        .limit(MAX_SITE_FACTS)
    ).all()
    return "\n".join(f"- {_cited(r, path)}" for r, path in rows) or "(aucune donnée de site)"


def _amount(value: Any) -> str:
    try:
        return f"{float(value):,.0f} € HT".replace(",", "\u202f")
    except (TypeError, ValueError):
        return "non précisé"


# ---------- starting -------------------------------------------------------------------------


def start_generation(db: Session, user: User, memoir: Memoir, queue: JobQueue) -> None:
    if memoir.status != "draft":
        raise ApiError(
            409,
            "memoir_not_draft",
            "Ce mémoire est déjà rédigé : régénérez un chapitre ou créez une nouvelle version.",
        )
    sections = db.scalars(select(MemoirSection).where(MemoirSection.memoir_id == memoir.id)).all()
    if not sections:
        raise ApiError(422, "empty_outline", "Le plan est vide.")
    memoir.status = "generating"
    for s in sections:
        s.status, s.error = "pending", None
        db.add(Job(kind=JOB_SECTION, ref_id=s.id, org_id=memoir.org_id, status="pending"))
    db.add(AuditLog(user_id=user.id, action="generate", entity="memoir", entity_id=memoir.id))
    db.commit()
    _enqueue_sections(db, memoir, [s.id for s in sections], queue)


def regenerate_section(
    db: Session,
    user: User,
    section: MemoirSection,
    instruction: str | None,
    add_refs: list[str],
    queue: JobQueue,
) -> None:
    """US-4.4 CA2: same prompt + the user's instruction + the previous version."""
    memoir = db.get_one(Memoir, section.memoir_id)
    if memoir.status == "draft":
        raise ApiError(409, "memoir_not_generated", "Lancez d'abord la rédaction du mémoire.")
    # A worker killed mid-job never resets "generating": past every timeout and retry, the
    # chapter must not stay locked forever.
    stale = section.updated_at < datetime.now(UTC) - SECTION_STALE_AFTER
    if section.status in ("pending", "generating") and not stale:
        raise ApiError(409, "section_busy", "Ce chapitre est en cours de rédaction.")
    if add_refs:
        known = set(
            db.scalars(
                select(Requirement.ref).where(Requirement.dce_analysis_id == memoir.dce_analysis_id)
            )
        )
        unknown = sorted(set(add_refs) - known)
        if unknown:
            raise ApiError(422, "unknown_requirement", f"Exigence inconnue : {', '.join(unknown)}.")
        section.requirement_refs = list(dict.fromkeys([*section.requirement_refs, *add_refs]))
    section.status, section.error, section.instruction = (
        "pending",
        None,
        (instruction or "").strip() or None,
    )
    memoir.status, memoir.conformity_status = "generating", "none"
    db.add(Job(kind=JOB_SECTION, ref_id=section.id, org_id=memoir.org_id, status="pending"))
    db.add(
        AuditLog(
            user_id=user.id,
            action="regenerate",
            entity="memoir_section",
            entity_id=section.id,
            meta={"instruction": section.instruction, "added_requirements": add_refs},
        )
    )
    db.commit()
    _enqueue_sections(db, memoir, [section.id], queue)


def _enqueue_sections(db: Session, memoir: Memoir, ids: list[uuid.UUID], queue: JobQueue) -> None:
    for section_id in ids:
        try:
            queue.enqueue_draft_section(section_id)
        except Exception:
            logger.exception("could not enqueue section %s", section_id)
            section = db.get_one(MemoirSection, section_id)
            section.status, section.error = (
                "error",
                "File d'attente indisponible : relancez ce chapitre.",
            )
            set_job_status(db, JOB_SECTION, section_id, "error", section.error)
            db.commit()
    _maybe_finish(db, memoir.id, queue)


# ---------- drafting one chapter (worker) ----------------------------------------------------


def run_draft_section(
    db: Session, section_id: uuid.UUID, embedder: Embedder, queue: JobQueue
) -> None:
    section = db.get(MemoirSection, section_id)
    if section is None:
        return
    scope_session(db, section.org_id)
    memoir = db.get_one(Memoir, section.memoir_id)
    analysis = db.get_one(DceAnalysis, memoir.dce_analysis_id)
    bid = db.get_one(Bid, memoir.bid_id)
    org = db.get_one(Organization, section.org_id)
    section.status = "generating"
    set_job_status(db, JOB_SECTION, section_id, "running")
    db.commit()

    data: dict[str, Any] = analysis.data or {}
    key_info = data.get("key_info") or {}
    requirements = _requirements(db, memoir, section.requirement_refs)
    req_block = (
        "\n".join(f"- [{r.ref}] {_cited(r, path)}" for r, path in requirements)
        or "(aucune exigence rattachée à ce chapitre)"
    )
    query = " ".join([section.title, *(r.text for r, _ in requirements)])
    try:
        hits = search_chunks(db, org, embedder, query, EXCERPTS_PER_CHAPTER)
    except (EmbeddingError, llm.LlmBudgetExceeded):
        hits = []  # the chapter is still drafted, from structured data only
    excerpts = {str(c.id): (c, title) for c, title, _ in hits}
    excerpt_block = (
        "\n".join(
            f'<excerpt id="{c.id}" source="{_tag_safe(title)}{f" p. {c.page_from}" if c.page_from else ""}">\n{_tag_safe(c.content)}\n</excerpt>'
            for c, title, _ in hits
        )
        or "(aucun extrait : la base documentaire est vide ou rien n'y correspond)"
    )
    company = company_data(db, org)
    references = _references(db, memoir)
    instruction = ""
    if section.instruction or section.content_md:
        instruction = (
            "Nouvelle version de ce chapitre. Consigne de l'entreprise : "
            f"{_tag_safe(section.instruction or 'améliorer le chapitre')}\n<previous>\n{_tag_safe(section.content_md or '')}\n</previous>"
        )

    prompt = load_prompt(CHAPTER_PROMPT)
    title_value = (key_info.get("title") or {}).get("value") or bid.title
    system, user = prompt.render(
        tender_title=_tag_safe(str(title_value)),
        buyer_name=_tag_safe(bid.buyer_name or "non précisé"),
        duration=_tag_safe(str((key_info.get("duration") or {}).get("value") or "non précisée")),
        amount=_amount((key_info.get("estimated_amount_eur_ht") or {}).get("value")),
        site_facts=_site_facts(db, memoir, section.requirement_refs),
        criterion=section.criterion_ref or "non précisé",
        weight=str(section.criterion_weight) if section.criterion_weight is not None else "?",
        section_title=section.title,
        word_budget=str(section.word_budget),
        requirements=req_block,
        company_structured_json=json.dumps(company, ensure_ascii=False, indent=1),
        company_excerpts=excerpt_block,
        references_json=json.dumps(references, ensure_ascii=False, indent=1),
        instruction=instruction,
    )
    try:
        result = llm.complete(
            db,
            org_id=org.id,
            task="memoir_generation",
            bid_id=bid.id,
            prompt_version=prompt.version,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_model=ChapterOut,
            max_tokens=max(2000, section.word_budget * 3),
        )
    except llm.LlmProviderError:
        _fail_section(
            db,
            section_id,
            "Service d'IA indisponible, nouvelle tentative en cours.",
            retrying=True,
            queue=queue,
        )
        raise
    except llm.LlmError as exc:
        _fail_section(db, section_id, str(exc), retrying=False, queue=queue)
        return

    out = result.data
    markdown = force_title(out.markdown, section.title)
    # What the model was given, as facts: an id in the tags is not a fact (a uuid can start
    # with "37"), the user's instruction is (« précisez nos 12 agents »).
    context = "\n".join(
        [
            req_block,
            *(f"{title} {c.content}" for c, title, _ in hits),
            json.dumps(company, ensure_ascii=False),
            json.dumps(references, ensure_ascii=False),
            str(title_value),
            bid.buyer_name or "",
            section.title,
            section.instruction or "",
        ]
    )
    flags = check_chapter(markdown, context, out.commitments, section.word_budget)
    fresh = db.get(MemoirSection, section_id, populate_existing=True, with_for_update=True)
    if fresh is None:  # memoir deleted meanwhile
        db.commit()
        return
    fresh.content_md = markdown
    fresh.covered_refs = [
        r for r in dict.fromkeys(out.covered_requirements) if r in fresh.requirement_refs
    ]
    fresh.sources = [
        {
            "chunk_id": s.excerpt_id,
            "document": excerpts[s.excerpt_id][1],
            "page": excerpts[s.excerpt_id][0].page_from,
            "used_for": s.used_for[:300],
        }
        for s in out.sources
        if s.excerpt_id in excerpts  # an unknown excerpt id is dropped, never shown
    ]
    fresh.flags = [{"type": f.type, "text": f.text, "term": f.term} for f in flags]
    fresh.generated_by_model, fresh.prompt_version = result.model, prompt.version
    add_revision(db, fresh, "generated", None, instruction=fresh.instruction)
    fresh.status, fresh.error, fresh.edited_by_user, fresh.instruction = "ready", None, False, None
    set_job_status(db, JOB_SECTION, section_id, "done")
    db.commit()
    _maybe_finish(db, fresh.memoir_id, queue)


def _fail_section(
    db: Session, section_id: uuid.UUID, message: str, retrying: bool, queue: JobQueue
) -> None:
    db.rollback()
    section = db.get(MemoirSection, section_id, populate_existing=True)
    if section is None:
        db.commit()
        return
    section.status = "generating" if retrying else "error"  # a retry is scheduled: not finished
    section.error = message
    set_job_status(db, JOB_SECTION, section_id, "pending" if retrying else "error", message)
    db.commit()
    if not retrying:
        _maybe_finish(db, section.memoir_id, queue)


def _maybe_finish(db: Session, memoir_id: uuid.UUID, queue: JobQueue) -> None:
    """When no chapter is still being drafted, the memoir is ready (and the matrix starts)."""
    memoir = db.get(Memoir, memoir_id, populate_existing=True, with_for_update=True)  # serialize
    if memoir is None or memoir.status != "generating":
        db.commit()
        return
    statuses = list(
        db.scalars(select(MemoirSection.status).where(MemoirSection.memoir_id == memoir_id))
    )
    if any(s in ("pending", "generating") for s in statuses):
        db.commit()
        return
    memoir.status = "ready"
    start = all(s == "ready" for s in statuses)
    if start:
        memoir.conformity_status, memoir.conformity_error = "pending", None
        db.add(Job(kind=JOB_CONFORMITY, ref_id=memoir.id, org_id=memoir.org_id, status="pending"))
    db.commit()
    if start:
        try:
            queue.enqueue_conformity(memoir_id)
        except Exception:
            logger.exception("could not enqueue conformity of %s", memoir_id)
            memoir.conformity_status, memoir.conformity_error = (
                "error",
                "File d'attente indisponible.",
            )
            db.commit()


# ---------- conformity matrix (worker) ------------------------------------------------------


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def request_conformity(db: Session, memoir: Memoir, queue: JobQueue) -> None:
    if memoir.status not in ("ready", "exported"):
        raise ApiError(409, "memoir_busy", "Le mémoire n'est pas encore rédigé.")
    if memoir.conformity_status == "pending":
        raise ApiError(409, "conformity_running", "La vérification est déjà en cours.")
    memoir.conformity_status, memoir.conformity_error = "pending", None
    db.add(Job(kind=JOB_CONFORMITY, ref_id=memoir.id, org_id=memoir.org_id, status="pending"))
    db.commit()
    queue.enqueue_conformity(memoir.id)


def run_conformity(db: Session, memoir_id: uuid.UUID) -> None:
    memoir = db.get(Memoir, memoir_id)
    if memoir is None:
        return
    scope_session(db, memoir.org_id)
    set_job_status(db, JOB_CONFORMITY, memoir_id, "running")
    db.commit()
    sections = db.scalars(
        select(MemoirSection)
        .where(MemoirSection.memoir_id == memoir_id)
        .order_by(MemoirSection.position)
    ).all()
    requirements = db.scalars(
        select(Requirement)
        .where(Requirement.dce_analysis_id == memoir.dce_analysis_id)
        .order_by(Requirement.position)
    ).all()
    by_ref = {r.ref: r for r in requirements}
    texts = {str(s.id): _squash(s.content_md or "") for s in sections}
    checked = {s.id: s.revision for s in sections}
    items: dict[str, dict[str, Any]] = {}
    error: str | None = None
    if requirements:
        prompt = load_prompt(MATRIX_PROMPT)
        system, user = prompt.render(
            requirements="\n".join(f"- [{r.ref}] {_tag_safe(r.text)}" for r in requirements),
            sections="\n".join(
                f'<section id="{s.id}" title="{_tag_safe(s.title)}">\n{_tag_safe(s.content_md or "")}\n</section>'
                for s in sections
            ),
        )
        try:
            result = llm.complete(
                db,
                org_id=memoir.org_id,
                task="memoir_generation",
                bid_id=memoir.bid_id,
                prompt_version=prompt.version,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_model=MatrixOut,
                max_tokens=8000,
            )
            for item in result.data.items:
                if item.requirement_ref not in by_ref or item.requirement_ref in items:
                    continue
                status, comment, section_id = item.status, item.comment, item.section_id
                excerpt = (item.excerpt or "").strip() or None
                if section_id not in texts:
                    section_id = None
                if excerpt:
                    home = [sid for sid, t in texts.items() if _squash(excerpt) in t]
                    if home:
                        section_id = section_id if section_id in home else home[0]
                    else:  # the model "quoted" something the memoir does not say
                        excerpt = None
                        if status == "covered":
                            status, comment = "partial", "Extrait cité introuvable : à vérifier."
                elif status == "covered":  # "covered" needs a quote from the memoir as proof
                    status, comment = "partial", "Aucun extrait cité : à vérifier."
                items[item.requirement_ref] = {
                    "status": status,
                    "section_id": section_id,
                    "excerpt": excerpt,
                    "comment": comment,
                    "method": "ai",
                }
        except llm.LlmProviderError:
            memoir_fresh = db.get_one(Memoir, memoir_id, populate_existing=True)
            memoir_fresh.conformity_error = (
                "Service d'IA indisponible, nouvelle tentative en cours."
            )
            db.commit()
            raise
        except llm.LlmError as exc:
            error = (
                f"Vérification automatique impossible ({exc}) : statuts déclarés par les chapitres."
            )

    # Fallback / completion: what each chapter declares it covers (never "covered" by default).
    declared = {ref: s for s in sections for ref in s.covered_refs}
    for r in requirements:
        if r.ref not in items:
            s = declared.get(r.ref)
            items[r.ref] = {
                "status": "partial" if s else "missing",
                "section_id": str(s.id) if s else None,
                "excerpt": None,
                "comment": (
                    "Déclarée traitée par le chapitre, non vérifiée."
                    if s
                    else "Non traitée dans le mémoire."
                ),
                "method": "declared",
            }
    for old in db.scalars(select(ConformityItem).where(ConformityItem.memoir_id == memoir_id)):
        db.delete(old)
    db.flush()
    for ref, entry in items.items():
        db.add(
            ConformityItem(
                memoir_id=memoir_id,
                requirement_id=by_ref[ref].id,
                section_id=uuid.UUID(entry["section_id"]) if entry["section_id"] else None,
                status=entry["status"],
                excerpt=(entry["excerpt"] or "")[:500] or None,
                comment=(entry["comment"] or "")[:500] or None,
                method=entry["method"],
            )
        )
    memoir = db.get_one(Memoir, memoir_id, populate_existing=True)
    now = {
        section_id: revision
        for section_id, revision in db.execute(
            select(MemoirSection.id, MemoirSection.revision).where(
                MemoirSection.memoir_id == memoir_id
            )
        )
    }
    # A chapter edited while the matrix was computed: the result is already outdated.
    memoir.conformity_status = "ready" if now == checked else "stale"
    memoir.conformity_error = error
    set_job_status(db, JOB_CONFORMITY, memoir_id, "done")
    db.commit()
