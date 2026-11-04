"""AI analysis of a DCE version (US-3.2) with verified sources (CLAUDE.md §5.2)."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
    ComplianceDocument,
    DceAnalysis,
    DceFile,
    DcePage,
    DceVersion,
    Job,
    Organization,
    Requirement,
)
from app.domain import go_no_go as gng
from app.domain import vault as vault_rules
from app.domain.trades import TRADES
from app.schemas.dce_analysis import DceAnalysisData, Source
from app.services import vault as vault_svc
from app.services.jobs import set_job_status
from app.workers.queue import ANALYSIS_JOB_TIMEOUT_SECONDS, JobQueue

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
_GENERAL_SCOPES = (SCOPE_FULL, SCOPE_NO_REQUIREMENTS)


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
        else:
            warnings.append(f"« {doc.name} » n'a pas pu être analysé : DCE trop volumineux.")
        used = budget
    calls = (
        [
            Call(
                SCOPE_NO_REQUIREMENTS if cctps else SCOPE_FULL,
                "\n\n".join(parts),
                frozenset(sent),
            )
        ]
        if parts
        else []  # only an oversized CCTP: no empty call for the other rubrics
    )
    general = len(calls)

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
            f"DCE très volumineux : seules les {max_calls - general} premières tranches du CCTP ont été analysées."
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

    visit, sv = out["site_visit"], data.site_visit
    if sv.mandatory is not None or sv.dates or sv.details:
        verified = src.resolve(sv.source)
        if verified is None:
            out["site_visit"] = {"mandatory": None, "dates": [], "details": None, "source": None}
            warnings.append("Visite : information écartée faute de source vérifiable.")
        else:
            visit["source"] = verified
    else:
        visit["source"] = None  # nothing to cite: never keep an unverified source

    memoir, mr = out["memoir_requirements"], data.memoir_requirements
    if (
        mr.imposed_outline
        or mr.max_pages
        or mr.format_constraints
        or mr.response_template_provided is not None
    ):
        verified = src.resolve(mr.source)
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
    else:
        memoir["source"] = None

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
            DceAnalysis.bid_id == bid.id,
            DceAnalysis.status.in_(("pending", "processing")),
            DceAnalysis.updated_at
            > datetime.now(UTC) - timedelta(seconds=2 * ANALYSIS_JOB_TIMEOUT_SECONDS),
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
        if not calls:
            raise llm.LlmError("DCE trop volumineux : aucune pièce n'a pu être analysée.")
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
        _fail(
            db,
            analysis_id,
            "Service d'IA indisponible, nouvelle tentative en cours.",
            retrying=True,
        )
        raise  # transient: RQ retries
    except llm.LlmError as exc:  # not configured, budget, invalid output, no text: permanent
        _fail(db, analysis_id, str(exc))
        return

    general = [r for c, r in zip(calls, results, strict=True) if c.scope in _GENERAL_SCOPES]
    slices = [r for c, r in zip(calls, results, strict=True) if c.scope not in _GENERAL_SCOPES]
    merged = general[0] if general else DceAnalysisData()
    if slices:
        merged.requirements = [r for res in slices for r in res.requirements]
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
    bid = db.get_one(Bid, fresh.bid_id)
    prefill_bid(bid, data, warnings)
    _, opinion = review(db, org, bid, data)
    fresh.go_no_go_score = opinion.score
    fresh.data, fresh.warnings, fresh.calls = data, warnings, len(calls)
    fresh.model, fresh.prompt_version, fresh.status = model, prompt.version, "ready"
    set_job_status(db, JOB_KIND, analysis_id, "done")
    db.commit()


def _fail(db: Session, analysis_id: uuid.UUID, message: str, retrying: bool = False) -> None:
    """``retrying``: RQ will run the job again, so the analysis stays "processing"."""
    db.rollback()
    analysis = db.get(DceAnalysis, analysis_id, populate_existing=True)
    if analysis is not None:
        analysis.status, analysis.error = ("processing" if retrying else "error"), message
        set_job_status(db, JOB_KIND, analysis_id, "pending" if retrying else "error", message)
    db.commit()


# ---------- review: vault cross-check (CA5), Go / No-Go (US-3.3), bid pre-fill -------------

PARIS = ZoneInfo("Europe/Paris")


def parse_datetime(value: str | None) -> datetime | None:
    """ISO 8601 from the model; a date without time means end of day, Paris time."""
    if not value:
        return None
    text = value.strip()
    try:
        if len(text) == 10:  # "2026-12-15": a whole day, not midnight
            parsed = datetime.combine(date.fromisoformat(text), time(23, 59))
        else:
            parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=PARIS)


def _value(data: dict[str, Any], *path: str) -> Any:
    node: Any = data
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def review(
    db: Session, org: Organization, bid: Bid, data: dict[str, Any]
) -> tuple[list[gng.DocumentCheck], gng.Opinion]:
    """Computed at read time: the vault, the profile and the clock all move."""
    today = vault_rules.paris_today()
    vault = [
        gng.VaultEntry(d.kind, vault_svc.to_out(d, org, today).status, d.valid_until)
        for d in db.scalars(select(ComplianceDocument))
    ]
    # The bid's deadline wins: it is pre-filled from the DCE and may have been corrected since
    # (amendment notice); the DCE value is the fallback.
    deadline = bid.deadline_at or parse_datetime(
        _value(data, "key_info", "submission_deadline", "value")
    )
    documents = gng.check_documents(
        [
            (d["name"], d["phase"], d.get("compliance_kind"))
            for d in data.get("required_documents", [])
        ],
        vault,
        deadline,
    )
    profile = db.scalar(select(CompanyProfile))
    trade_keywords = [
        k for t in (profile.trades if profile else []) if t in TRADES for k in TRADES[t].keywords
    ]
    amount = _value(data, "key_info", "estimated_amount_eur_ht", "value")
    visit_dates = [
        d for d in (parse_datetime(x) for x in _value(data, "site_visit", "dates") or []) if d
    ]
    text = " ".join(
        [str(_value(data, "key_info", "title", "value") or ""), bid.title]
        + [r["text"] for r in data.get("requirements", [])]
    )
    opinion = gng.opinion(
        gng.Inputs(
            now=datetime.now(UTC),
            deadline=deadline,
            estimated_amount_cents=round(amount * 100) if isinstance(amount, int | float) else None,
            min_amount_cents=profile.min_amount_cents if profile else None,
            max_amount_cents=profile.max_amount_cents if profile else None,
            profile_keywords=[*(profile.keywords_include if profile else []), *trade_keywords],
            excluded_keywords=profile.keywords_exclude if profile else [],
            tender_text=text,
            documents=documents,
            blocking_watch_points=[
                w["text"] for w in data.get("watch_points", []) if w["severity"] == "blocking"
            ],
            visit_mandatory=_value(data, "site_visit", "mandatory"),
            visit_dates=visit_dates,
        )
    )
    return documents, opinion


def prefill_bid(bid: Bid, data: dict[str, Any], warnings: list[str]) -> None:
    """Fill what the user left empty; never overwrite what they typed (only warn)."""
    buyer = _value(data, "key_info", "buyer_name", "value")
    if buyer and not bid.buyer_name:
        bid.buyer_name = str(buyer)[:300]
    deadline = parse_datetime(_value(data, "key_info", "submission_deadline", "value"))
    if deadline is None:
        return
    if bid.deadline_at is None:
        bid.deadline_at = deadline
    elif abs((bid.deadline_at - deadline).total_seconds()) > 60:
        warnings.append(
            f"La date limite du DCE ({deadline.astimezone(PARIS):%d/%m/%Y %H:%M}) diffère de celle "
            f"du dossier ({bid.deadline_at.astimezone(PARIS):%d/%m/%Y %H:%M}) : vérifiez-la."
        )
