"""Phase 0 — compare AI models on real DCE (docs/11, tickets P0-02 to P0-06).

Each DCE of ``samples/`` goes through the **product's own pipeline** once per model: DCE
processing (text, OCR), analysis, outline, chapter drafting, conformity matrix, Word export.
Every (DCE, model) pair gets its own organization, so the AI journal (``ai_calls``) gives
its exact cost and duration. Outputs, in ``out_dir``:

* ``<dce>/memoire-<X>.docx`` and ``<dce>/analyse-<X>.json``: anonymized (letters drawn at
  random per DCE, docs/11 step 2), to send to the rater;
* ``grille-de-notation.xlsx``: the rating grid of docs/11, one row per memoir;
* ``correspondance-a-garder.json``: which letter is which model — never sent to the rater;
* ``rapport.md``: cost, duration, failures, extraction metrics against ``attendu.json``.

Layout of ``samples/`` (not versioned)::

    samples/entreprise.json        the company (profile, staff, equipment, references…)
    samples/base/*.docx|pdf        its knowledge base ("modele*" = memoir template)
    samples/<dce>/dce/*            the DCE as received (ZIP or files)
    samples/<dce>/attendu.json     optional: the expected analysis sheet (docs/11)
"""

import io
import json
import logging
import random
import re
import secrets
import unicodedata
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, BinaryIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.embeddings import get_embedder
from app.core import runtime
from app.core.config import get_settings
from app.core.tenancy import scope_session
from app.db.models import (
    AiCall,
    Bid,
    Certification,
    CompanyReference,
    ConformityItem,
    DceAnalysis,
    DceVersion,
    Equipment,
    HumanResource,
    Memoir,
    MemoirSection,
    Organization,
    User,
)
from app.documents.ocr import OcrEngine
from app.domain.markdown import TODO
from app.exports.memoir_docx import build_memoir
from app.platform_settings import TASK_MODELS
from app.schemas.profile import (
    CertificationIn,
    EquipmentIn,
    HumanResourceIn,
    ProfileIn,
    ReferenceIn,
)
from app.services import credits
from app.services import dce as dce_svc
from app.services import knowledge as knowledge_svc
from app.services import memoir as memoir_svc
from app.services import memoir_drafting as drafting
from app.services.dce_analysis import run_analyze_dce
from app.services.exports import memoir_data
from app.services.profile import get_or_create_profile, refresh_completeness, update_profile

logger = logging.getLogger("pilao.evaluation")
EVALUATION_CREDITS = 100_000  # far more than one passage spends: the balance never stops a run
DCE_SUFFIXES = {".zip", ".pdf", ".docx", ".xlsx", ".odt", ".doc", ".ods", ".xls"}
CRITERIA = [  # docs/11 — rating grid, out of 10 each
    ("Conformité au plan", "Le plan imposé par le RC est-il respecté ?"),
    ("Réponse au CCTP", "Les exigences du CCTP sont-elles toutes traitées, concrètement ?"),
    ("Adaptation au chantier", "Le texte parle-t-il de ce site et pas d'un site générique ?"),
    ("Exactitude", "Aucune information fausse ou inventée sur l'entreprise ?"),
    ("Qualité de rédaction", "Français professionnel, clair, sans répétitions ?"),
    ("Utilisabilité", "Temps pour le rendre envoyable (10 = moins de 30 min) ?"),
]
SessionFactory = Callable[[], Session]


# ---------- in-process stand-ins for the workers ---------------------------------------


class LocalStorage:
    """Object storage on the local disk (evaluation only)."""

    def __init__(self, root: Path) -> None:
        self._root = root
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self._root / key.replace("/", "__")

    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        fileobj.seek(0)
        self._path(key).write_bytes(fileobj.read())
        fileobj.seek(0)

    def get(self, key: str) -> BinaryIO:
        return io.BytesIO(self._path(key).read_bytes())

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str:
        return self._path(key).as_uri()


class TrustedScanner:
    """The company's own DCE, on the evaluator's machine: no antivirus pass."""

    def scan(self, fileobj: BinaryIO) -> str | None:
        return None


@dataclass
class InlineQueue:
    """The jobs the pipeline enqueues, run in order by ``drain`` (as the RQ workers would)."""

    sessions: SessionFactory
    storage: LocalStorage
    ocr: OcrEngine | None = None
    jobs: list[tuple[str, uuid.UUID]] = field(default_factory=list)

    def _add(self, kind: str, ref: uuid.UUID) -> None:
        self.jobs.append((kind, ref))

    def enqueue_index_document(self, doc_id: uuid.UUID) -> None:
        self._add("index", doc_id)

    def enqueue_read_compliance_document(self, doc_id: uuid.UUID) -> None:
        pass  # no attestation in an evaluation

    def enqueue_process_dce(self, version_id: uuid.UUID) -> None:
        self._add("process", version_id)

    def enqueue_analyze_dce(self, analysis_id: uuid.UUID) -> None:
        self._add("analyze", analysis_id)

    def enqueue_draft_section(self, section_id: uuid.UUID) -> None:
        self._add("draft", section_id)

    def enqueue_conformity(self, memoir_id: uuid.UUID) -> None:
        self._add("conformity", memoir_id)

    def enqueue_export(self, document_id: uuid.UUID) -> None:
        pass

    def enqueue_match_tenders(self, tender_ids: list[uuid.UUID]) -> None:
        pass

    def enqueue_rematch_org(self, org_id: uuid.UUID) -> None:
        pass

    def enqueue_score_tenders(self, org_id: uuid.UUID) -> None:
        pass

    def enqueue_org_export(self, request_id: uuid.UUID) -> None:
        pass

    def enqueue_profile_prefill(self, org_id: uuid.UUID) -> None:
        pass  # the model comparison does not pre-fill profiles

    def enqueue_import_source(self, source: str) -> None:
        pass  # nor imports notices

    def drain(self) -> None:
        embedder = get_embedder()
        while self.jobs:
            kind, ref = self.jobs.pop(0)
            with self.sessions() as db:
                try:
                    if kind == "index":
                        knowledge_svc.run_index_document(db, ref, self.storage, embedder)
                    elif kind == "process":
                        dce_svc.run_process_dce(
                            db, ref, self.storage, TrustedScanner(), self.ocr, queue=self
                        )
                    elif kind == "analyze":
                        run_analyze_dce(db, ref)
                    elif kind == "draft":
                        drafting.run_draft_section(db, ref, embedder, self)
                    elif kind == "conformity":
                        drafting.run_conformity(db, ref)
                except Exception:  # a provider outage: recorded as such, the run goes on
                    logger.exception("evaluation job %s %s failed", kind, ref)


# ---------- metrics against the expected sheet (docs/11) -------------------------------

_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    """Accents ignored: OCR and some PDFs lose them, the expected sheet keeps them."""
    plain = "".join(
        ch for ch in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(ch)
    )
    return {w for w in _WORD.findall(plain) if len(w) > 2}


def similar(a: str, b: str, threshold: float = 0.4) -> bool:
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= threshold


def _get(data: dict[str, Any], *path: str) -> Any:
    for key in path:
        data = data.get(key) if isinstance(data, dict) else None  # type: ignore[assignment]
    return data


def _value(data: dict[str, Any], *path: str) -> Any:
    item = _get(data, *path)
    return item.get("value") if isinstance(item, dict) else item


def compare(expected: dict[str, Any], got: dict[str, Any]) -> dict[str, Any]:
    """Key fields right, CCTP requirements found (recall), and their cited pages."""
    fields: dict[str, bool] = {}

    def text_field(name: str, *path: str) -> None:
        want = _value(expected, *path)
        if want:
            fields[name] = similar(str(want), str(_value(got, *path) or ""), 0.6)

    text_field("acheteur", "key_info", "buyer_name")
    text_field("objet", "key_info", "title")
    deadline = _value(expected, "key_info", "submission_deadline")
    if deadline:
        have = str(_value(got, "key_info", "submission_deadline") or "")
        fields["date limite"] = have[:16].replace(" ", "T") == str(deadline)[:16].replace(" ", "T")
    amount = _value(expected, "key_info", "estimated_amount_eur_ht")
    if amount:
        have_amount = _value(got, "key_info", "estimated_amount_eur_ht")
        fields["montant estimé"] = bool(have_amount) and abs(
            float(have_amount) - float(amount)
        ) <= 0.01 * float(amount)
    visit = _get(expected, "site_visit", "mandatory")
    if visit is not None:
        fields["visite obligatoire"] = _get(got, "site_visit", "mandatory") == visit
    pages = _get(expected, "memoir_requirements", "max_pages")
    if pages is not None:
        fields["pages max"] = _get(got, "memoir_requirements", "max_pages") == pages
    outline = _get(expected, "memoir_requirements", "imposed_outline")
    if outline is not None:
        have_outline = _get(got, "memoir_requirements", "imposed_outline") or []
        fields["plan imposé"] = len(outline) == len(have_outline) and all(
            similar(a, b, 0.6) for a, b in zip(outline, have_outline, strict=False)
        )
    criteria = expected.get("award_criteria")
    if criteria:
        have_criteria = got.get("award_criteria") or []
        fields["critères"] = all(
            any(
                similar(c["name"], h.get("name", ""), 0.5)
                and (c.get("weight_pct") is None or h.get("weight_pct") == c.get("weight_pct"))
                for h in have_criteria
            )
            for c in criteria
        )

    wanted = expected.get("requirements") or []
    extracted = got.get("requirements") or []
    found, pages_right, pages_known = 0, 0, 0
    for req in wanted:
        match = next((r for r in extracted if similar(req["text"], r.get("text", ""))), None)
        if match is None:
            continue
        found += 1
        want_page = (req.get("source") or {}).get("page")
        if want_page is not None:
            pages_known += 1
            pages_right += (match.get("source") or {}).get("page") == want_page
    return {
        "champs": fields,
        "champs_pct": round(100 * sum(fields.values()) / len(fields)) if fields else None,
        "exigences_rappel_pct": round(100 * found / len(wanted)) if wanted else None,
        "sources_pct": round(100 * pages_right / pages_known) if pages_known else None,
    }


# ---------- one run: a DCE with a model ------------------------------------------------


@contextmanager
def models(model: str) -> Iterator[None]:
    """The same model for every generative task of the run."""
    s = get_settings()
    saved = (s.llm_model_extraction, s.llm_model_generation, s.llm_model_scoring)
    s.llm_model_extraction = s.llm_model_generation = s.llm_model_scoring = model
    # lot 5: a model set in the administration would otherwise win over the one under test
    tasks = {f"model.{task}": model for task in TASK_MODELS if task != "compliance_reading"}
    try:
        with runtime.overridden(tasks):
            yield
    finally:
        s.llm_model_extraction, s.llm_model_generation, s.llm_model_scoring = saved


def _siret() -> str:
    """A valid (Luhn) SIRET for an evaluation organization, new at every run.

    Never drawn from ``--seed``: running the same evaluation twice on the same base would
    otherwise create the same SIRET, which is unique.
    """
    base = f"9{secrets.randbelow(10**12):012d}"
    for digit in range(10):
        candidate = base + str(digit)
        total = 0
        for i, ch in enumerate(reversed(candidate)):
            n = int(ch) * (2 if i % 2 else 1)
            total += n - 9 if n > 9 else n
        if total % 10 == 0:
            return candidate
    raise AssertionError("unreachable")


ITEMS = (
    (HumanResource, HumanResourceIn, "human_resources"),
    (Equipment, EquipmentIn, "equipment"),
    (Certification, CertificationIn, "certifications"),
    (CompanyReference, ReferenceIn, "references"),
)


def check_company(data: dict[str, Any]) -> None:
    """``entreprise.json`` is read with the profile forms' own rules, before any run."""
    try:
        ProfileIn.model_validate(data.get("profile") or {})
        for _, schema, key in ITEMS:
            for item in data.get(key) or []:
                schema.model_validate(item)
    except ValidationError as exc:
        raise ValueError(f"entreprise.json invalide : {exc}") from exc


def _company(db: Session, data: dict[str, Any]) -> tuple[Organization, User]:
    siret = _siret()
    org = Organization(
        siren=siret[:9],
        siret=siret,
        name=data.get("name") or "Entreprise évaluée",  # as in the memoir: no label
        legal_form=data.get("legal_form"),
        address_line=data.get("address_line"),
        postal_code=data.get("postal_code"),
        city=data.get("city"),
    )
    db.add(org)
    db.flush()
    scope_session(db, org.id)  # as a request of this company: org_id set on every row
    user = User(
        org_id=org.id,
        email=f"evaluation-{uuid.uuid4().hex[:12]}@pilao.invalid",
        full_name="Évaluation phase 0",
        role="org_admin",
        email_verified_at=datetime.now(UTC),
    )
    db.add(user)
    db.flush()
    get_or_create_profile(db, org)
    update_profile(db, org, user.id, ProfileIn.model_validate(data.get("profile") or {}))
    for model, schema, key in ITEMS:
        for item in data.get(key) or []:
            db.add(model(org_id=org.id, **schema.model_validate(item).model_dump()))
    db.flush()
    refresh_completeness(db, org)
    # the evaluation measures the models, never the balance: every paid step goes through
    credits.grant(db, org, EVALUATION_CREDITS, "Évaluation", None)
    db.commit()
    return org, user


@dataclass
class Run:
    dce: str
    model: str
    letter: str
    analysis_status: str = "absent"
    analysis: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    chapters: int = 0
    drafted: int = 0
    to_complete: int = 0
    conformity: dict[str, int] = field(default_factory=dict)
    cost_eur: dict[str, float] = field(default_factory=dict)
    seconds: dict[str, float] = field(default_factory=dict)
    failed_calls: int = 0
    metrics: dict[str, Any] | None = None
    error: str | None = None
    org_id: uuid.UUID | None = None


def _collect_ai(db: Session, run: Run, org_id: uuid.UUID) -> None:
    for task, cost, ms, failures in db.execute(
        select(
            AiCall.task,
            func.coalesce(func.sum(AiCall.cost_eur), Decimal(0)),
            func.coalesce(func.sum(AiCall.latency_ms), 0),
            func.count().filter(AiCall.success.is_(False)),
        )
        .where(AiCall.org_id == org_id)
        .group_by(AiCall.task)
    ):
        run.cost_eur[task] = round(float(cost), 4)
        run.seconds[task] = round(ms / 1000, 1)
        run.failed_calls += int(failures)


def evaluate_one(
    sessions: SessionFactory,
    queue: InlineQueue,
    sample: Path,
    company: dict[str, Any],
    knowledge: list[Path],
    model: str,
    letter: str,
    out: Path,
) -> Run:
    """One DCE with one model, every queued job included (they read the model settings)."""
    run = Run(dce=sample.name, model=model, letter=letter)
    try:
        with models(model):
            _run_pipeline(sessions, queue, sample, company, knowledge, letter, out, run)
    except Exception as exc:  # a broken DCE stops this run only: the others go on
        logger.exception("evaluation of %s with %s failed", sample.name, model)
        queue.jobs.clear()
        run.error = f"passage interrompu : {getattr(exc, 'message', None) or exc}"
    if run.org_id is not None:
        with sessions() as db:
            _collect_ai(db, run, run.org_id)
    return run


def _run_pipeline(
    sessions: SessionFactory,
    queue: InlineQueue,
    sample: Path,
    company: dict[str, Any],
    knowledge: list[Path],
    letter: str,
    out: Path,
    run: Run,
) -> None:
    with sessions() as db:
        org, user = _company(db, company)
        org_id, user_id = org.id, user.id
        run.org_id = org_id
        for path in knowledge:
            kind = "memoir_template" if path.stem.lower().startswith("modele") else "past_memoir"
            with path.open("rb") as fh:
                knowledge_svc.create_document(
                    db, org, user, fh, path.name, kind, None, queue.storage, TrustedScanner(), queue
                )
        queue.drain()
        bid = Bid(org_id=org_id, title=sample.name, owner_user_id=user_id, status="to_review")
        db.add(bid)
        db.commit()
        handles = [
            p.open("rb")
            for p in sorted((sample / "dce").iterdir())
            if p.suffix.lower() in DCE_SUFFIXES
        ]
        try:
            dce_svc.create_version(
                db,
                org,
                user,
                bid,
                [(h, Path(h.name).name) for h in handles],
                queue.storage,
                TrustedScanner(),
                queue,
            )
        finally:
            for h in handles:
                h.close()
        bid_id = bid.id
    queue.drain()  # processing, then the analysis it starts

    with sessions() as db:
        org = db.get_one(Organization, org_id)
        scope_session(db, org_id)
        user = db.get_one(User, user_id)
        bid = db.get_one(Bid, bid_id)
        version = db.scalars(select(DceVersion).where(DceVersion.bid_id == bid_id)).first()
        analysis = db.scalars(select(DceAnalysis).where(DceAnalysis.bid_id == bid_id)).first()
        if version is not None and version.status != "ready":
            run.error = f"DCE non traité : {version.error}"
        if analysis is not None:
            run.analysis_status, run.warnings = analysis.status, list(analysis.warnings or [])
            run.analysis = analysis.data or {}
            if analysis.status != "ready":
                run.error = f"analyse en échec : {analysis.error}"
        if run.analysis_status == "ready":
            memoir = memoir_svc.create_memoir(db, user, bid, get_embedder())
            drafting.start_generation(db, user, memoir, queue)
            memoir_id = memoir.id
    if run.analysis_status == "ready":
        queue.drain()  # chapters, then the conformity matrix
        with sessions() as db:
            scope_session(db, org_id)
            memoir = db.get_one(Memoir, memoir_id)
            sections = db.scalars(
                select(MemoirSection).where(MemoirSection.memoir_id == memoir_id)
            ).all()
            run.chapters = len(sections)
            run.drafted = sum(s.status == "ready" for s in sections)
            run.to_complete = sum(len(TODO.findall(s.content_md or "")) for s in sections)
            for status, count in db.execute(
                select(ConformityItem.status, func.count())
                .where(ConformityItem.memoir_id == memoir_id)
                .group_by(ConformityItem.status)
            ):
                run.conformity[status] = int(count)
            org = db.get_one(Organization, org_id)
            bid = db.get_one(Bid, bid_id)
            target = out / sample.name
            target.mkdir(parents=True, exist_ok=True)
            data = memoir_data(db, org, memoir, bid, queue.storage)
            (target / f"memoire-{letter}.docx").write_bytes(build_memoir(data).to_bytes())
    target = out / sample.name
    target.mkdir(parents=True, exist_ok=True)
    (target / f"analyse-{letter}.json").write_text(
        json.dumps(run.analysis, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    expected = sample / "attendu.json"
    if expected.exists() and run.analysis:
        run.metrics = compare(json.loads(expected.read_text(encoding="utf-8")), run.analysis)


# ---------- the whole evaluation -------------------------------------------------------


def _grid(path: Path, runs: list[Run]) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Notation"
    headers = ["DCE", "Mémoire", *(c for c, _ in CRITERIA), "Moyenne", "Commentaire"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for i, run in enumerate(sorted(runs, key=lambda r: (r.dce, r.letter)), start=2):
        first, last = "C", chr(ord("C") + len(CRITERIA) - 1)
        ws.append(
            [
                run.dce,
                run.letter,
                *([None] * len(CRITERIA)),
                f'=IFERROR(AVERAGE({first}{i}:{last}{i}),"")',
                None,
            ]
        )
    for column, width in zip("ABCDEFGHIJ", (22, 10, 14, 14, 14, 14, 14, 14, 10, 40), strict=True):
        ws.column_dimensions[column].width = width
    guide = wb.create_sheet("Consignes")
    guide.append(["Critère (note sur 10)", "Question"])
    for name, question in CRITERIA:
        guide.append([name, question])
    guide.append([])
    guide.append(["Seuil V1", "Moyenne ≥ 7/10 et aucune note < 5 en « Exactitude »."])
    guide.append(["Anonymat", "Les lettres sont tirées au hasard pour chaque DCE."])
    guide.column_dimensions["A"].width, guide.column_dimensions["B"].width = 28, 80
    wb.save(path)


def _report(path: Path, runs: list[Run], started: datetime) -> None:
    by_model: dict[str, list[Run]] = {}
    for run in runs:
        by_model.setdefault(run.model, []).append(run)
    lines = [
        f"# Phase 0 — comparaison des modèles ({started:%d/%m/%Y %H:%M} UTC)",
        "",
        (
            "Coûts en euros (journal `ai_calls`), durées cumulées des appels, métriques "
            "d'extraction calculées contre `attendu.json` quand il existe (docs/11)."
        ),
        "",
        (
            "| Modèle | Coût total | Analyse | Rédaction | Durée totale | Appels en échec | "
            "Chapitres rédigés | [À COMPLÉTER] | Champs justes | Exigences retrouvées | "
            "Pages justes |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def avg(values: list[Any]) -> str:
        known = [v for v in values if v is not None]
        return f"{round(sum(known) / len(known))} %" if known else "—"

    for model, items in by_model.items():
        cost = sum(sum(r.cost_eur.values()) for r in items)
        analysis = sum(r.cost_eur.get("dce_extraction", 0) for r in items)
        drafting_cost = sum(r.cost_eur.get("memoir_generation", 0) for r in items)
        seconds = sum(sum(r.seconds.values()) for r in items)
        lines.append(
            f"| `{model}` | {cost:.2f} € | {analysis:.2f} € | {drafting_cost:.2f} € | "
            f"{seconds / 60:.1f} min | {sum(r.failed_calls for r in items)} | "
            f"{sum(r.drafted for r in items)}/{sum(r.chapters for r in items)} | "
            f"{sum(r.to_complete for r in items)} | "
            f"{avg([r.metrics and r.metrics['champs_pct'] for r in items])} | "
            f"{avg([r.metrics and r.metrics['exigences_rappel_pct'] for r in items])} | "
            f"{avg([r.metrics and r.metrics['sources_pct'] for r in items])} |"
        )
    lines += ["", "## Détail par DCE", ""]
    for run in sorted(runs, key=lambda r: (r.dce, r.letter)):
        conformity = ", ".join(f"{k} {v}" for k, v in sorted(run.conformity.items())) or "—"
        lines.append(
            f"- **{run.dce} / {run.letter}** (`{run.model}`) : analyse {run.analysis_status}, "
            f"{run.drafted}/{run.chapters} chapitres, conformité : {conformity}, "
            f"{sum(run.cost_eur.values()):.3f} €" + (f" — **{run.error}**" if run.error else "")
        )
        if run.metrics:
            wrong = [k for k, ok in run.metrics["champs"].items() if not ok]
            if wrong:
                lines.append(f"  - champs à revoir : {', '.join(wrong)}")
    lines += [
        "",
        (
            "Les lettres sont en clair ici : ce rapport et `correspondance-a-garder.json` ne "
            "vont pas au noteur (Abdraouf reçoit les mémoires et la grille seulement)."
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_evaluation(
    samples: Path,
    model_names: list[str],
    out: Path,
    sessions: SessionFactory,
    ocr: OcrEngine | None = None,
    seed: int | None = None,
) -> list[Run]:
    if not 1 <= len(model_names) <= 6:
        raise ValueError("de 1 à 6 modèles")
    company = (
        json.loads((samples / "entreprise.json").read_text(encoding="utf-8"))
        if (samples / "entreprise.json").exists()
        else {}
    )
    check_company(company)
    base = samples / "base"
    knowledge = (
        sorted(p for p in base.iterdir() if p.suffix.lower() in {".pdf", ".docx", ".odt", ".doc"})
        if base.is_dir()
        else []
    )
    dces = sorted(p for p in samples.iterdir() if (p / "dce").is_dir())
    if not dces:
        raise ValueError(f"aucun DCE dans {samples} (attendu : <dossier>/dce/…)")
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    queue = InlineQueue(sessions, LocalStorage(out / ".stockage"), ocr)
    started = datetime.now(UTC)
    runs: list[Run] = []
    mapping: dict[str, dict[str, str]] = {}
    for sample in dces:
        letters = [chr(ord("A") + i) for i in range(len(model_names))]
        rng.shuffle(letters)
        mapping[sample.name] = {}
        for model, letter in zip(model_names, letters, strict=True):
            logger.info("évaluation de %s avec %s (%s)", sample.name, model, letter)
            runs.append(
                evaluate_one(
                    sessions,
                    queue,
                    sample,
                    company,
                    knowledge,
                    model,
                    letter,
                    out,
                )
            )
            mapping[sample.name][letter] = model
    (out / "correspondance-a-garder.json").write_text(
        json.dumps(mapping, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    _grid(out / "grille-de-notation.xlsx", runs)
    _report(out / "rapport.md", runs, started)
    return runs
