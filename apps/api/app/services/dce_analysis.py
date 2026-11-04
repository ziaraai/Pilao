"""AI analysis of a DCE version (US-3.2) with verified sources (CLAUDE.md §5.2)."""

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import llm
from app.ai.prompts import load_prompt
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    Bid,
    CompanyProfile,
    DceAnalysis,
    DceFile,
    DcePage,
    DceVersion,
    Job,
    Organization,
    Requirement,
)
from app.domain.trades import TRADES
from app.schemas.dce_analysis import DceAnalysisData, Source
from app.services.jobs import set_job_status
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.dce_analysis")
JOB_KIND = "analyze_dce"
TASK = "dce_extraction"
PROMPT = "extraction_dce"
MAX_OUTPUT_TOKENS = 16_000
# Order in which pieces are given to the model when everything does not fit.
PRIORITY = {"rc": 0, "ccap": 1, "ae": 2, "annex": 3, "other": 4, "cctp": 5}
PRICE_KINDS = ("bpu", "dpgf", "dqe")  # pricing is out of the V1 scope
SCHEMA_PATH = Path(get_settings().prompts_dir).parent / "schemas" / "dce_analysis.schema.json"

SCOPE_FULL = "produis la fiche complète, toutes rubriques comprises."
SCOPE_NO_REQUIREMENTS = (
    "remplis toutes les rubriques SAUF `requirements`, que tu laisses vide (le CCTP est "
    "analysé séparément)."
)
SCOPE_REQUIREMENTS = (
    "ne remplis QUE `requirements` à partir de cet extrait du CCTP ({pages}) ; laisse les "
    "autres rubriques vides ou nulles."
)


# ---------- documents sent to the model ---------------------------------------------------


@dataclass
class Doc:
    dce_file_id: uuid.UUID
    name: str
    kind: str
    paginated: bool
    pages: list[tuple[int, str]] = field(default_factory=list)

    @property
    def size(self) -> int:
        return sum(len(t) for _, t in self.pages)


def _neutralize(text: str) -> str:
    """A document must not be able to close its own <document> tag (prompt injection)."""
    return text.replace("<document", "‹document").replace("</document", "‹/document")


def render(doc: Doc, pages: list[tuple[int, str]] | None = None) -> str:
    body = []
    for number, text in pages if pages is not None else doc.pages:
        body.append(
            f"[[PAGE {number}]]\n{_neutralize(text)}" if doc.paginated else _neutralize(text)
        )
    name = doc.name.replace('"', "'")
    return f'<document name="{name}" kind="{doc.kind}">\n' + "\n".join(body) + "\n</document>"


def load_docs(db: Session, version: DceVersion) -> tuple[list[Doc], list[str]]:
    warnings: list[str] = []
    docs: list[Doc] = []
    files = db.scalars(
        select(DceFile).where(DceFile.dce_version_id == version.id).order_by(DceFile.path)
    )
    for f in files:
        if f.detected_kind in PRICE_KINDS:
            warnings.append(
                f"« {f.path} » ({f.detected_kind.upper()}) n'est pas analysé : chiffrage hors périmètre."
            )
            continue
        if f.text_status == "ocr_unavailable":
            warnings.append(
                f"« {f.path} » est scanné et n'a pas pu être lu : son contenu manque à l'analyse."
            )
        pages = db.execute(
            select(DcePage.page, DcePage.text)
            .where(DcePage.dce_file_id == f.id)
            .order_by(DcePage.page)
        ).all()
        doc = Doc(
            f.id, f.path, f.detected_kind, f.paginated, [(p, t) for p, t in pages if t.strip()]
        )
        if doc.pages:
            docs.append(doc)
    docs.sort(key=lambda d: (PRIORITY.get(d.kind, 4), d.name))
    return docs, warnings


@dataclass(frozen=True)
class Call:
    scope: str
    documents: str
    sent: frozenset[tuple[str, int]] = frozenset()  # (file name, page) given to the model


def _sent(doc: Doc, pages: list[tuple[int, str]] | None = None) -> set[tuple[str, int]]:
    return {(doc.name, p) for p, _ in (pages if pages is not None else doc.pages)}


def plan_calls(docs: list[Doc], budget: int, max_calls: int) -> tuple[list[Call], list[str]]:
    """One call if everything fits; otherwise the RC/CCAP/annexes, then the CCTP in slices."""
    warnings: list[str] = []
    if sum(d.size for d in docs) <= budget:
        everything = frozenset(pair for d in docs for pair in _sent(d))
        return [Call(SCOPE_FULL, "\n\n".join(render(d) for d in docs), everything)], warnings

    others = [d for d in docs if d.kind != "cctp"]
    cctps = [d for d in docs if d.kind == "cctp"]
    parts, used = [], 0
    sent: set[tuple[str, int]] = set()
    for doc in others:
        if used + doc.size <= budget:
            parts.append(render(doc))
            sent |= _sent(doc)
            used += doc.size
            continue
        kept, room = [], budget - used
        for number, text in doc.pages:
            if len(text) > room:
                break
            kept.append((number, text))
            room -= len(text)
        if kept:
            parts.append(render(doc, kept))
            sent |= _sent(doc, kept)
        warnings.append(
            f"« {doc.name} » est trop long : seules ses premières pages ont été analysées."
        )
        used = budget
    calls = [
        Call(SCOPE_NO_REQUIREMENTS if cctps else SCOPE_FULL, "\n\n".join(parts), frozenset(sent))
    ]

    for doc in cctps:
        window: list[tuple[int, str]] = []
        size = 0
        for number, text in doc.pages:
            if window and size + len(text) > budget:
                calls.append(_cctp_call(doc, window))
                window, size = [], 0
            window.append((number, text[:budget]))
            size += min(len(text), budget)
        if window:
            calls.append(_cctp_call(doc, window))
    if len(calls) > max_calls:
        warnings.append(
            f"DCE très volumineux : seules les {max_calls - 1} premières tranches du CCTP ont été analysées."
        )
        calls = calls[:max_calls]
    return calls, warnings


def _cctp_call(doc: Doc, window: list[tuple[int, str]]) -> Call:
    pages = f"pages {window[0][0]} à {window[-1][0]}" if doc.paginated else "document entier"
    return Call(
        SCOPE_REQUIREMENTS.format(pages=pages), render(doc, window), frozenset(_sent(doc, window))
    )


# ---------- source verification -----------------------------------------------------------


class _Sources:
    def __init__(self, docs: list[Doc], sent: set[tuple[str, int]] | None = None) -> None:
        self.sent = sent
        self.by_name = {d.name: d for d in docs}
        self.by_base: dict[str, Doc | None] = {}
        for d in docs:
            base = d.name.rsplit("/", 1)[-1]
            self.by_base[base] = None if base in self.by_base else d  # ambiguous -> None

    def resolve(self, source: Source | None) -> dict[str, Any] | None:
        """The verified source as stored ({file, page, dce_file_id}), or None if unverifiable."""
        if source is None:
            return None
        doc = self.by_name.get(source.file) or self.by_base.get(source.file.rsplit("/", 1)[-1])
        if doc is None:
            return None
        pages = {p for p, _ in doc.pages}
        if self.sent is not None:  # only what the model actually received can be cited
            pages = {p for name, p in self.sent if name == doc.name}
            if not doc.paginated and not pages:
                return None
        if doc.paginated:
            if source.page is None or source.page not in pages:
                return None
        elif source.page not in (None, 1):
            return None
        return {
            "file": doc.name,
            "page": source.page if doc.paginated else None,
            "dce_file_id": str(doc.dce_file_id),
        }


def verify(
    data: DceAnalysisData, docs: list[Doc], sent: set[tuple[str, int]] | None = None
) -> tuple[dict[str, Any], list[str]]:
    """Keep only what carries a verifiable source; say what was dropped.

    ``sent`` restricts sources to the (file, page) pairs really given to the model.
    """
    src = _Sources(docs, sent)
    warnings: list[str] = []
    out: dict[str, Any] = data.model_dump(mode="json")

    def sourced_field(container: dict[str, Any], key: str, label: str, obj: Any) -> None:
        if obj is None or obj.value in (None, ""):
            container[key] = None
            return
        verified = src.resolve(obj.source)
        if verified is None:
            container[key] = None
            warnings.append(f"{label} : valeur écartée faute de source vérifiable.")
        else:
            container[key] = {"value": obj.value, "source": verified}

    key_info = out["key_info"]
    for key, label in (
        ("buyer_name", "Acheteur"),
        ("title", "Objet"),
        ("procedure", "Procédure"),
        ("estimated_amount_eur_ht", "Montant estimé"),
        ("duration", "Durée"),
        ("submission_deadline", "Date limite de remise"),
        ("submission_platform", "Plateforme de dépôt"),
    ):
        sourced_field(key_info, key, label, getattr(data.key_info, key))
    sourced_field(out, "questions_deadline", "Date limite des questions", data.questions_deadline)

    def sourced_list(
        key: str, items: list[Any], label: str, container: dict[str, Any] | None = None
    ) -> None:
        target = container if container is not None else out
        kept = []
        for item, raw in zip(items, target[key], strict=True):
            verified = src.resolve(item.source)
            if verified is None:
                warnings.append(
                    f"{label} écarté(e) faute de source vérifiable : « {_short(raw)} »."
                )
                continue
            raw["source"] = verified
            kept.append(raw)
        target[key] = kept

    sourced_list("lots", data.key_info.lots, "Lot", key_info)
    sourced_list("award_criteria", data.award_criteria, "Critère")
    sourced_list("required_documents", data.required_documents, "Pièce demandée")
    sourced_list("requirements", data.requirements, "Exigence")
    sourced_list("watch_points", data.watch_points, "Point de vigilance")

    visit = out["site_visit"]
    if data.site_visit.mandatory is not None or data.site_visit.dates:
        verified = src.resolve(data.site_visit.source)
        if verified is None:
            out["site_visit"] = {"mandatory": None, "dates": [], "details": None, "source": None}
            warnings.append("Visite : information écartée faute de source vérifiable.")
        else:
            visit["source"] = verified

    memoir = out["memoir_requirements"]
    if data.memoir_requirements.imposed_outline or data.memoir_requirements.max_pages:
        verified = src.resolve(data.memoir_requirements.source)
        if verified is None:
            # The imposed outline drives the whole memoir (CLAUDE.md §5.4): never trust it unsourced.
            out["memoir_requirements"] = {
                "imposed_outline": [],
                "response_template_provided": None,
                "max_pages": None,
                "format_constraints": None,
                "source": None,
            }
            warnings.append(
                "Plan imposé / nombre de pages : écartés faute de source vérifiable, à vérifier dans le RC."
            )
        else:
            memoir["source"] = verified

    for i, req in enumerate(out["requirements"], start=1):  # stable, gap-free numbering
        req["ref"] = f"CCTP-{i}"
    return out, warnings


def _short(raw: dict[str, Any]) -> str:
    text = str(raw.get("text") or raw.get("name") or raw.get("title") or "")
    return text[:80] + ("…" if len(text) > 80 else "")


# ---------- orchestration -----------------------------------------------------------------


def request_analysis(db: Session, version: DceVersion, queue: JobQueue) -> DceAnalysis:
    analysis = DceAnalysis(
        id=uuid.uuid4(),
        bid_id=version.bid_id,
        dce_version_id=version.id,
        status="pending",
        org_id=version.org_id,
    )
    db.add(analysis)
    db.add(Job(kind=JOB_KIND, ref_id=analysis.id, org_id=version.org_id, status="pending"))
    db.commit()
    try:
        queue.enqueue_analyze_dce(analysis.id)
    except Exception:
        logger.exception("could not enqueue analysis %s", analysis.id)
        analysis.status, analysis.error = (
            "error",
            "File d'attente indisponible. Relancez l'analyse.",
        )
        set_job_status(db, JOB_KIND, analysis.id, "error", analysis.error)
        db.commit()
    return analysis


def rerun(db: Session, bid: Bid, queue: JobQueue) -> DceAnalysis:
    running = db.scalar(
        select(DceAnalysis.id).where(
            DceAnalysis.bid_id == bid.id, DceAnalysis.status.in_(("pending", "processing"))
        )
    )
    if running is not None:
        raise ApiError(409, "analysis_running", "Une analyse est déjà en cours.")
    version = db.scalars(
        select(DceVersion)
        .where(DceVersion.bid_id == bid.id, DceVersion.status == "ready")
        .order_by(DceVersion.version.desc())
    ).first()
    if version is None:
        raise ApiError(
            409, "no_dce", "Déposez d'abord un DCE (et attendez la fin de son traitement)."
        )
    return request_analysis(db, version, queue)


def _company_summary(db: Session, org: Organization) -> str:
    profile = db.scalar(select(CompanyProfile))
    trades = [TRADES[t].label for t in (profile.trades if profile else []) if t in TRADES]
    departments = (
        ", ".join(profile.departments) if profile and profile.departments else "non précisés"
    )
    return f"{org.name} — métiers : {', '.join(trades) or 'non précisés'} — départements : {departments}"


def run_analyze_dce(db: Session, analysis_id: uuid.UUID) -> None:
    analysis = db.get(DceAnalysis, analysis_id)
    if analysis is None:
        return
    scope_session(db, analysis.org_id)
    org = db.get_one(Organization, analysis.org_id)
    version = db.get_one(DceVersion, analysis.dce_version_id)
    analysis.status, analysis.error = "processing", None
    set_job_status(db, JOB_KIND, analysis_id, "running")
    db.commit()

    s = get_settings()
    docs, warnings = load_docs(db, version)
    try:
        if not docs:
            raise llm.LlmError("Aucun texte exploitable dans ce DCE.")
        calls, plan_warnings = plan_calls(docs, s.dce_analysis_max_chars, s.dce_analysis_max_calls)
        warnings += plan_warnings
        prompt = load_prompt(PROMPT)
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        company = _company_summary(db, org)
        results: list[DceAnalysisData] = []
        model = ""
        for call in calls:
            system, user = prompt.render(
                company_summary=company,
                documents=call.documents,
                scope=call.scope,
                json_schema=schema,
            )
            result = llm.complete(
                db,
                org_id=org.id,
                task=TASK,
                bid_id=analysis.bid_id,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_model=DceAnalysisData,
                prompt_version=prompt.version,
                max_tokens=MAX_OUTPUT_TOKENS,
            )
            results.append(result.data)
            model = result.model
    except llm.LlmProviderError:
        _fail(db, analysis_id, "Service d'IA indisponible, nouvelle tentative en cours.")
        raise  # transient: RQ retries
    except llm.LlmError as exc:  # not configured, budget, invalid output, no text: permanent
        _fail(db, analysis_id, str(exc))
        return

    merged = results[0]
    if len(results) > 1:
        merged.requirements = [r for res in results[1:] for r in res.requirements]
    sent = set().union(*(c.sent for c in calls))
    data, source_warnings = verify(merged, docs, sent)
    warnings += source_warnings

    fresh = db.get(DceAnalysis, analysis_id, populate_existing=True)
    if fresh is None:  # bid deleted meanwhile
        db.commit()
        return
    for position, req in enumerate(data["requirements"]):
        db.add(
            Requirement(
                bid_id=fresh.bid_id,
                dce_analysis_id=fresh.id,
                position=position,
                ref=req["ref"],
                text=req["text"],
                category=req["category"],
                importance=req["importance"],
                source_file_id=uuid.UUID(req["source"]["dce_file_id"]),
                page=req["source"]["page"],
            )
        )
    fresh.data, fresh.warnings, fresh.calls = data, warnings, len(calls)
    fresh.model, fresh.prompt_version, fresh.status = model, prompt.version, "ready"
    set_job_status(db, JOB_KIND, analysis_id, "done")
    db.commit()


def _fail(db: Session, analysis_id: uuid.UUID, message: str) -> None:
    db.rollback()
    analysis = db.get(DceAnalysis, analysis_id, populate_existing=True)
    if analysis is not None:
        analysis.status, analysis.error = "error", message
        set_job_status(db, JOB_KIND, analysis_id, "error", message)
    db.commit()
