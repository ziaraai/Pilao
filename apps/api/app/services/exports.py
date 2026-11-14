"""Export of the memoir: Word, PDF, complete ZIP folder (US-4.6, P2-07).

Before an export, the user is warned of what remains (US-4.6 CA4): ``[À COMPLÉTER]``
markers, CCTP requirements missing from the memoir, an outdated conformity matrix,
undrafted chapters, a page count over the limit. The API refuses the export until the user
has acknowledged those warnings; they are kept with the exported file.

The files are built by the worker (LibreOffice takes seconds; the ZIP reads every
attestation from the object storage).
"""

import logging
import math
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    AuditLog,
    Bid,
    ComplianceDocument,
    ConformityItem,
    DceAnalysis,
    File,
    GeneratedDocument,
    Job,
    Memoir,
    MemoirSection,
    Organization,
    Requirement,
    User,
)
from app.domain.imposed_font import ImposedFont
from app.domain.imposed_font import from_analysis as font_from_analysis
from app.domain.markdown import TODO
from app.domain.memoir_checks import count_words
from app.domain.memoir_plan import words_per_page
from app.exports.bundle import build_zip, safe_name
from app.exports.dc_forms import FORMS, PROOF_LABELS, french_date
from app.exports.memoir_docx import Chapter, MemoirExportData, RequirementRow, build_memoir
from app.exports.pdf import PdfConverter, PdfUnavailable
from app.services.documents import (
    DOCX_MIME,
    PARIS,
    form_data,
    latest_analysis,
    load_logo,
    save_file,
    today_paris,
)
from app.services.jobs import set_job_status
from app.services.vault import usable_documents
from app.storage.objects import ObjectStorage
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.exports")
JOB_EXPORT = "export_memoir"
FORMATS = {"docx": "memoir_docx", "pdf": "memoir_pdf", "zip": "bundle_zip"}
MIMES = {"memoir_docx": (DOCX_MIME, "docx"), "memoir_pdf": ("application/pdf", "pdf")}
ZIP_MIME = "application/zip"


@dataclass
class ExportCheck:
    to_complete: list[tuple[MemoirSection, list[str]]] = field(default_factory=list)
    missing: list[Requirement] = field(default_factory=list)
    not_drafted: list[str] = field(default_factory=list)
    conformity_status: str = "none"
    pages: int | None = None
    max_pages: int | None = None

    @property
    def warnings(self) -> list[str]:
        out = []
        if self.to_complete:
            count = sum(len(items) for _, items in self.to_complete)
            titles = ", ".join(s.title for s, _ in self.to_complete)
            out.append(f"{count} « [À COMPLÉTER] » restent dans : {titles}.")
        if self.missing:
            out.append(
                f"{len(self.missing)} exigence{'s' if len(self.missing) > 1 else ''} du CCTP "
                f"absente{'s' if len(self.missing) > 1 else ''} du mémoire : "
                + ", ".join(r.ref for r in self.missing)
                + "."
            )
        if self.not_drafted:
            out.append("Chapitres non rédigés : " + ", ".join(self.not_drafted) + ".")
        status_note = {
            "none": "La matrice de conformité n'a pas été faite.",
            "stale": "La matrice de conformité date d'avant vos dernières modifications.",
            "pending": "La matrice de conformité est en cours de vérification.",
            "error": "La matrice de conformité a échoué.",
        }.get(self.conformity_status)
        if status_note:
            out.append(status_note)
        if self.pages and self.max_pages and self.pages > self.max_pages:
            out.append(f"Environ {self.pages} pages pour {self.max_pages} autorisées.")
        return out


def imposed_font(db: Session, memoir: Memoir) -> ImposedFont | None:
    """The font the RC of the memoir's DCE imposes, read from its format constraints."""
    analysis = db.get(DceAnalysis, memoir.dce_analysis_id)
    return font_from_analysis(analysis.data or {}) if analysis is not None else None


def estimated_pages(db: Session, memoir: Memoir, words: int) -> int | None:
    font = imposed_font(db, memoir)
    return math.ceil(words / words_per_page(font.size if font else None)) if words else None


def _sections(db: Session, memoir: Memoir) -> list[MemoirSection]:
    return list(
        db.scalars(
            select(MemoirSection)
            .where(MemoirSection.memoir_id == memoir.id)
            .order_by(MemoirSection.position)
        )
    )


def export_check(db: Session, memoir: Memoir) -> ExportCheck:
    sections = _sections(db, memoir)
    check = ExportCheck(conformity_status=memoir.conformity_status, max_pages=memoir.max_pages)
    for s in sections:
        if not s.content_md:
            check.not_drafted.append(s.title)
            continue
        items = [m.group(1).strip() for m in TODO.finditer(s.content_md)]
        if items:
            check.to_complete.append((s, items))
    check.missing = list(
        db.scalars(
            select(Requirement)
            .join(ConformityItem, ConformityItem.requirement_id == Requirement.id)
            .where(ConformityItem.memoir_id == memoir.id, ConformityItem.status == "missing")
            .order_by(Requirement.position)
        )
    )
    words = sum(count_words(s.content_md or "") for s in sections)
    check.pages = estimated_pages(db, memoir, words)
    return check


def request_export(
    db: Session,
    user: User,
    memoir: Memoir,
    fmt: str,
    acknowledged: bool,
    queue: JobQueue,
) -> GeneratedDocument:
    if memoir.status == "draft":
        raise ApiError(409, "memoir_not_generated", "Lancez d'abord la rédaction du mémoire.")
    if memoir.status == "generating":
        raise ApiError(409, "memoir_busy", "Attendez la fin de la rédaction en cours.")
    warnings = export_check(db, memoir).warnings
    if warnings and not acknowledged:
        raise ApiError(
            409,
            "export_needs_confirmation",
            "Des points restent à traiter : " + " ".join(warnings),
        )
    doc = GeneratedDocument(
        id=uuid.uuid4(),
        org_id=memoir.org_id,
        bid_id=memoir.bid_id,
        memoir_id=memoir.id,
        kind=FORMATS[fmt],
        status="pending",
        warnings=warnings,
        created_by=user.id,
    )
    db.add(doc)
    db.add(Job(kind=JOB_EXPORT, ref_id=doc.id, org_id=memoir.org_id, status="pending"))
    db.add(
        AuditLog(
            user_id=user.id,
            action="export",
            entity="memoir",
            entity_id=memoir.id,
            meta={"format": fmt, "warnings": warnings},
        )
    )
    db.commit()
    try:
        queue.enqueue_export(doc.id)
    except Exception:
        logger.exception("could not enqueue export %s", doc.id)
        doc.status, doc.error = "error", "File d'attente indisponible : relancez l'export."
        set_job_status(db, JOB_EXPORT, doc.id, "error", doc.error)
        db.commit()
    return doc


# ---------- building (worker) ---------------------------------------------------------


def memoir_data(
    db: Session, org: Organization, memoir: Memoir, bid: Bid, storage: ObjectStorage
) -> MemoirExportData:
    sections = _sections(db, memoir)
    analysis = latest_analysis(db, bid)
    key_info = ((analysis.data if analysis else None) or {}).get("key_info") or {}
    title = (key_info.get("title") or {}).get("value") or bid.title
    buyer = (key_info.get("buyer_name") or {}).get("value") or bid.buyer_name
    titles = {s.id: s.title for s in sections}
    quoted = {
        requirement_id: titles.get(section_id) if section_id else None
        for requirement_id, section_id in db.execute(
            select(ConformityItem.requirement_id, ConformityItem.section_id).where(
                ConformityItem.memoir_id == memoir.id, ConformityItem.status != "missing"
            )
        )
    }
    planned = {ref: s.title for s in sections for ref in s.requirement_refs}
    requirements = db.scalars(
        select(Requirement)
        .where(Requirement.dce_analysis_id == memoir.dce_analysis_id)
        .order_by(Requirement.position)
    ).all()
    return MemoirExportData(
        company=org.name,
        tender_title=str(title),
        buyer=str(buyer) if buyer else None,
        reference=bid.reference,
        lot=bid.lot_label,
        version=memoir.version,
        exported_at=datetime.now(UTC).astimezone(PARIS),
        chapters=[Chapter(s.title, s.content_md) for s in sections],
        requirements=[
            RequirementRow(r.ref, r.text, quoted.get(r.id) or planned.get(r.ref))
            for r in requirements
        ],
        brand_color=org.brand_color,
        logo=load_logo(db, org, storage),
        font=font.name if (font := imposed_font(db, memoir)) else None,
        font_size=font.size if font else None,
    )


def _readme(
    title: str, warnings: list[str], contents: list[str], notes: list[str], excluded: list[str]
) -> bytes:
    lines = [
        f"Dossier de réponse — {title}",
        f"Préparé avec Pilao le {french_date(today_paris())}.",
        "",
        "BROUILLON À RELIRE : l'entreprise reste responsable du contenu et des engagements de",
        "son offre. Pilao ne dépose jamais l'offre à votre place.",
        "",
        "Contenu :",
        *(f"- {c}" for c in contents),
    ]
    if warnings or notes:
        lines += ["", "Points à vérifier avant le dépôt :", *(f"- {w}" for w in warnings + notes)]
    if excluded:
        lines += [
            "",
            "Attestations non jointes (non confirmées, expirées ou au nom d'un autre SIREN) :",
            *(f"- {e}" for e in excluded),
        ]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8-sig")  # readable in Windows Notepad


def _bundle(
    db: Session,
    org: Organization,
    bid: Bid,
    doc: GeneratedDocument,
    docx: bytes,
    data: MemoirExportData,
    storage: ObjectStorage,
    converter: PdfConverter,
) -> bytes:
    entries: list[tuple[str, bytes]] = [("01 - Mémoire technique.docx", docx)]
    contents, notes = ["01 - Mémoire technique (Word"], []
    try:
        entries.append(("01 - Mémoire technique.pdf", converter.convert(docx)))
        contents[0] += " et PDF)"
    except PdfUnavailable as exc:
        contents[0] += ")"
        notes.append(f"PDF non joint ({exc}) : exportez-le depuis Word.")
    creator = db.get(User, doc.created_by) if doc.created_by else None
    forms = form_data(db, org, creator.email if creator else None, bid, storage)
    for label, build in FORMS.values():
        builder = build(forms)
        entries.append((f"02 - Pièces administratives/{label}.docx", builder.to_bytes()))
        if builder.to_complete:
            notes.append(f"{label} : {len(builder.to_complete)} point(s) à compléter.")
    contents.append("02 - Pièces administratives : " + ", ".join(lbl for lbl, _ in FORMS.values()))
    usable = usable_documents(db, org, today_paris())
    for proof in usable:
        record = db.get(File, proof.file_id)
        if record is None:
            continue
        label = PROOF_LABELS.get(proof.kind, proof.kind)
        name = f"03 - Attestations/{label} - {record.filename}"
        entries.append((name, storage.get(record.storage_key).read()))
    contents.append(f"03 - Attestations : {len(usable)} document(s) à jour du coffre-fort")
    kept = {p.id for p in usable}
    excluded = [
        PROOF_LABELS.get(d.kind, d.kind)
        for d in db.scalars(select(ComplianceDocument).order_by(ComplianceDocument.created_at))
        if d.id not in kept
    ]
    entries.append(
        ("LISEZ-MOI.txt", _readme(data.tender_title, doc.warnings, contents, notes, excluded))
    )
    return build_zip(entries)


def run_export(
    db: Session, doc_id: uuid.UUID, storage: ObjectStorage, converter: PdfConverter
) -> None:
    doc = db.get(GeneratedDocument, doc_id)
    if doc is None or doc.memoir_id is None:
        return
    scope_session(db, doc.org_id)
    org = db.get_one(Organization, doc.org_id)
    memoir = db.get_one(Memoir, doc.memoir_id)
    bid = db.get_one(Bid, doc.bid_id)
    set_job_status(db, JOB_EXPORT, doc_id, "running")
    db.commit()

    data = memoir_data(db, org, memoir, bid, storage)
    builder = build_memoir(data)
    docx = builder.to_bytes()
    base = safe_name(f"Mémoire technique - {bid.title[:80]} - v{memoir.version}")
    try:
        if doc.kind == "memoir_docx":
            content, (mime, ext) = docx, MIMES["memoir_docx"]
        elif doc.kind == "memoir_pdf":
            content, (mime, ext) = converter.convert(docx), MIMES["memoir_pdf"]
        else:
            content = _bundle(db, org, bid, doc, docx, data, storage, converter)
            mime, ext = ZIP_MIME, "zip"
            base = safe_name(f"Dossier de réponse - {bid.title[:80]}")
    except PdfUnavailable as exc:  # permanent: the Word file is still there to export
        db.rollback()
        failed = db.get_one(GeneratedDocument, doc_id, populate_existing=True)
        failed.status = "error"
        failed.error = f"{exc} Téléchargez le Word et enregistrez-le en PDF depuis Word."
        set_job_status(db, JOB_EXPORT, doc_id, "error", failed.error)
        db.commit()
        return

    doc.to_complete = builder.to_complete
    memoir.status = "exported"
    set_job_status(db, JOB_EXPORT, doc_id, "done")
    save_file(db, org, doc, content, f"{base}.{ext}", mime, ext, storage)
