"""Pre-filled documents of a bid (US-4.5, P2-06) and the storage of every generated file."""

import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import (
    AuditLog,
    Bid,
    Certification,
    CompanyProfile,
    CompanyReference,
    DceAnalysis,
    Equipment,
    File,
    GeneratedDocument,
    HumanResource,
    Memoir,
    Organization,
    User,
)
from app.domain.company import vat_number
from app.exports import dc_forms
from app.services.files import discard_object, store_generated
from app.services.vault import usable_documents
from app.storage.objects import ObjectStorage

logger = logging.getLogger("pilao.documents")
PARIS = ZoneInfo("Europe/Paris")
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
KEEP_PER_KIND = 3  # older files of the same kind are deleted (storage quota)


def _source(item: Any) -> str | None:
    src = (item or {}).get("source") if isinstance(item, dict) else None
    if not src or not src.get("file"):
        return None
    return f"{src['file']}{f' p. {src['page']}' if src.get('page') else ''}"


def _sourced(item: Any) -> dc_forms.Sourced:
    value = item.get("value") if isinstance(item, dict) else None
    return dc_forms.Sourced(str(value) if value not in (None, "") else None, _source(item))


def paris(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    local = dt.astimezone(PARIS)
    return f"{dc_forms.french_date(local.date())} à {local:%H:%M}"


def latest_analysis(db: Session, bid: Bid) -> DceAnalysis | None:
    return db.scalars(
        select(DceAnalysis)
        .where(DceAnalysis.bid_id == bid.id, DceAnalysis.status == "ready")
        .order_by(DceAnalysis.created_at.desc())
    ).first()


def load_logo(db: Session, org: Organization, storage: ObjectStorage) -> bytes | None:
    if org.logo_file_id is None:
        return None
    record = db.get(File, org.logo_file_id)
    if record is None or record.mime not in ("image/png", "image/jpeg"):
        return None
    try:
        return storage.get(record.storage_key).read()
    except Exception:  # an unreadable logo must not block the document
        logger.exception("could not read the logo of %s", org.id)
        return None


def form_data(
    db: Session, org: Organization, user: User, bid: Bid, storage: ObjectStorage
) -> dc_forms.FormData:
    """Everything a document may say: the company's own data and the analysed DCE."""
    analysis = latest_analysis(db, bid)
    data: dict[str, Any] = (analysis.data if analysis else None) or {}
    key_info = data.get("key_info") or {}
    profile = db.scalar(select(CompanyProfile))

    buyer = _sourced(key_info.get("buyer_name"))
    title = _sourced(key_info.get("title"))
    visit = data.get("site_visit") or {}
    visit_text = None
    if visit.get("mandatory") is not None or visit.get("dates"):
        visit_text = ("Obligatoire" if visit.get("mandatory") else "Facultative") + (
            f" : {', '.join(visit['dates'])}" if visit.get("dates") else ""
        )
    memoir = db.scalars(
        select(Memoir).where(Memoir.bid_id == bid.id).order_by(Memoir.version.desc())
    ).first()
    ref_query = select(CompanyReference).order_by(
        CompanyReference.year.desc().nulls_last(), CompanyReference.created_at
    )
    if memoir is not None and memoir.reference_ids:
        ref_query = ref_query.where(CompanyReference.id.in_(memoir.reference_ids))
    today = datetime.now(UTC).astimezone(PARIS).date()
    address = " ".join(x for x in (org.address_line, org.postal_code, org.city) if x) or None
    return dc_forms.FormData(
        company=dc_forms.Company(
            name=org.name,
            siret=org.siret,
            siren=org.siren,
            vat_number=vat_number(org.siren),
            legal_form=org.legal_form,
            address=address,
            naf_code=org.naf_code,
            phone=org.phone,
            email=org.contact_email or user.email,
            signatory_name=org.signatory_name,
            signatory_role=org.signatory_role,
            headcount_range=org.headcount_range,
        ),
        buyer=buyer if buyer.value else dc_forms.Sourced(bid.buyer_name),
        title=title if title.value else dc_forms.Sourced(bid.title),
        reference=bid.reference,
        lot=bid.lot_label,
        lots=[
            f"Lot {lot['number']} : {lot['title']}" if lot.get("number") else lot["title"]
            for lot in key_info.get("lots") or []
            if isinstance(lot, dict) and lot.get("title")
        ],
        deadline=dc_forms.Sourced(
            paris(bid.deadline_at), _source(key_info.get("submission_deadline"))
        ),
        duration=_sourced(key_info.get("duration")),
        site_visit=dc_forms.Sourced(visit_text, _source(visit)),
        revenues_cents=(
            [profile.revenue_y1_cents, profile.revenue_y2_cents, profile.revenue_y3_cents]
            if profile
            else []
        ),
        staff=[
            (h.qualification, h.count, h.description)
            for h in db.scalars(select(HumanResource).order_by(HumanResource.created_at))
        ],
        equipment=[
            (e.name, e.category, e.quantity)
            for e in db.scalars(select(Equipment).order_by(Equipment.created_at))
        ],
        certifications=[
            (c.name, c.number, c.valid_until)
            for c in db.scalars(select(Certification).order_by(Certification.created_at))
        ],
        references=[
            dc_forms.ReferenceRow(
                client=r.client_name,
                public=r.client_type == "public",
                title=r.title,
                location=r.location,
                year=r.year,
                amount_cents=r.amount_cents,
                duration_months=r.duration_months,
                description=r.description,
            )
            for r in db.scalars(ref_query)
        ],
        proofs=[(d.kind, d.valid_until) for d in usable_documents(db, org, today)],
        trades=list(profile.trades) if profile else [],
        brand_color=org.brand_color,
        logo=load_logo(db, org, storage),
    )


def file_title(label: str, bid: Bid, extension: str) -> str:
    return f"{label} - {bid.title[:80]}.{extension}"


def save_file(
    db: Session,
    org: Organization,
    doc: GeneratedDocument,
    content: bytes,
    filename: str,
    mime: str,
    extension: str,
    storage: ObjectStorage,
) -> None:
    """Attach ``content`` to ``doc`` (ready) and commit; older files of its kind are pruned."""
    record = store_generated(db, org, doc.created_by, content, filename, mime, extension, storage)
    doc.file_id, doc.status, doc.error = record.id, "ready", None
    try:
        db.commit()
    except Exception:
        db.rollback()
        discard_object(storage, record.storage_key)
        raise
    prune(db, doc, storage)


def prune(db: Session, doc: GeneratedDocument, storage: ObjectStorage) -> None:
    older = db.scalars(
        select(GeneratedDocument)
        .where(GeneratedDocument.bid_id == doc.bid_id, GeneratedDocument.kind == doc.kind)
        .order_by(GeneratedDocument.created_at.desc())
        .offset(KEEP_PER_KIND)
    ).all()
    keys = []
    for old in older:
        if old.file_id is not None and (record := db.get(File, old.file_id)) is not None:
            keys.append(record.storage_key)
            db.delete(record)
        db.delete(old)
    db.commit()
    for key in keys:
        discard_object(storage, key)


def generate_form(
    db: Session, org: Organization, user: User, bid: Bid, kind: str, storage: ObjectStorage
) -> GeneratedDocument:
    if kind not in dc_forms.FORMS:
        raise ApiError(404, "unknown_document", "Document inconnu.")
    label, build = dc_forms.FORMS[kind]
    builder = build(form_data(db, org, user, bid, storage))
    doc = GeneratedDocument(
        id=uuid.uuid4(),
        org_id=org.id,
        bid_id=bid.id,
        kind=kind,
        status="pending",
        to_complete=builder.to_complete,
        created_by=user.id,
    )
    db.add(doc)
    db.add(AuditLog(user_id=user.id, action="generate", entity="document", entity_id=doc.id))
    db.flush()
    save_file(
        db, org, doc, builder.to_bytes(), file_title(label, bid, "docx"), DOCX_MIME, "docx", storage
    )
    return doc


def today_paris() -> date:
    return datetime.now(UTC).astimezone(PARIS).date()
