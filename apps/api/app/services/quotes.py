"""The company's own quote for a consultation (ADR-052).

« Préparer le devis » (paid when a CCTP is read): the AI lists « Prestations comprises » from
the CCTP pages that name the rubriques priced, each bullet citing its page; the worker then
writes the quote in Word and PDF. Changing the validity, the VAT or the bullets only rebuilds
the files (free). The table always comes from the « Prix » tab: a quote waits for every price.
"""

import io
import logging
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import llm
from app.ai.prompts import load_prompt
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    AuditLog,
    Bid,
    DceFile,
    DcePage,
    DceVersion,
    File,
    Job,
    Organization,
    PriceSheet,
    Quote,
    User,
)
from app.domain.pricing import Priced, PriceLine
from app.domain.quote import (
    InclusionsOut,
    Page,
    QuoteTable,
    fingerprint,
    keep_sourced,
    pick_pages,
    quote_table,
    terms,
    vat_of,
)
from app.exports.pdf import PdfConverter, PdfUnavailable
from app.exports.quote_docx import Company, QuoteDocData, build_quote
from app.schemas.files import DownloadUrlOut
from app.schemas.quotes import InclusionItem, QuoteOut, QuoteSettingsIn, QuoteStateOut
from app.services import credits
from app.services import pricing as pricing_svc
from app.services.documents import DOCX_MIME, PARIS, load_logo
from app.services.files import delete_file, discard_object, store_generated
from app.services.jobs import set_job_status
from app.storage.objects import ObjectStorage
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.quotes")

JOB_DRAFT = "draft_quote"
TASK = "quote_draft"
PROMPT = "devis_prestations"
PDF_MIME = "application/pdf"
ZIP_MIME = "application/zip"
STALE_AFTER = timedelta(minutes=15)

NOT_CONSULTATION = "Le devis se prépare dans une consultation."
NO_PRICES = "Lisez d'abord le fichier de prix dans l'onglet Prix."
NOTHING_PRICED = "Aucune rubrique n'est chiffrée : reprenez-en une dans l'onglet Prix."
NOT_READY = "Le devis n'est pas prêt."
NO_PDF = "Le PDF n'a pas pu être fait : téléchargez le Word."
QUEUE_DOWN = "File d'attente indisponible : réessayez."
PROVIDER_DOWN = "Service d'IA indisponible : réessayez."
FAILED = "Le devis n'a pas pu être préparé : réessayez."
INTERRUPTED = "La préparation du devis a été interrompue : réessayez."


# ---------- what the quote is made of -------------------------------------------------------


def _sheet(db: Session, bid: Bid) -> tuple[PriceSheet, list[PriceLine], Priced] | None:
    """The price file the quote is made from: the ready one with the largest total (a BPU
    without quantities totals nothing; a DQE of the same lines does)."""
    files = [f.id for f in pricing_svc.price_files(db, bid)]
    sheets = db.scalars(
        select(PriceSheet)
        .where(PriceSheet.dce_file_id.in_(files), PriceSheet.status == "ready")
        .order_by(PriceSheet.created_at)
    ).all()
    best: tuple[PriceSheet, list[PriceLine], Priced] | None = None
    for sheet in sheets:
        lines, priced = pricing_svc.priced_sheet(db, sheet)
        if best is None or priced.total_cents > best[2].total_cents:
            best = (sheet, lines, priced)
    return best


def blocking(db: Session, bid: Bid) -> tuple[str, str] | None:
    """(code, message) when no quote can be prepared now."""
    if bid.kind != "consultation":
        return "not_consultation", NOT_CONSULTATION
    found = _sheet(db, bid)
    if found is None:
        return "no_prices", NO_PRICES
    _, lines, priced = found
    if priced.missing_count:
        n = priced.missing_count
        return "prices_missing", f"Il reste {n} prix à saisir dans l'onglet Prix."
    if not quote_table(lines, priced).rows:
        return "nothing_priced", NOTHING_PRICED
    return None


def _cctp_pages(db: Session, bid: Bid) -> list[Page]:
    version = db.scalars(
        select(DceVersion)
        .where(DceVersion.bid_id == bid.id, DceVersion.status == "ready")
        .order_by(DceVersion.version.desc())
    ).first()
    if version is None:
        return []
    rows = db.execute(
        select(DceFile.path, DcePage.page, DcePage.text)
        .join(DcePage, DcePage.dce_file_id == DceFile.id)
        .where(DceFile.dce_version_id == version.id, DceFile.detected_kind == "cctp")
        .order_by(DceFile.path, DcePage.page)
    ).all()
    return [Page(path.rsplit("/", 1)[-1], page, text) for path, page, text in rows if text.strip()]


def _pages_to_send(db: Session, bid: Bid, table: QuoteTable) -> list[Page]:
    words = terms([r.section for r in table.rows] + [r.label for r in table.rows])
    return pick_pages(_cctp_pages(db, bid), words)


# ---------- reading ------------------------------------------------------------------------


def get_quote(db: Session, bid: Bid) -> Quote | None:
    return db.scalar(select(Quote).where(Quote.bid_id == bid.id))


def quote_out(db: Session, bid: Bid, quote: Quote) -> QuoteOut:
    found = _sheet(db, bid)
    table = quote_table(found[1], found[2]) if found else None
    ht = table.total_ht_cents if table and table.has_totals else None
    vat = vat_of(ht, quote.vat_bp) if ht is not None else None
    stale = (
        table is not None and quote.status == "ready" and quote.priced_hash != fingerprint(table)
    )
    return QuoteOut(
        id=quote.id,
        number=quote.number,
        proposed_number=quote.proposed_number,
        status=quote.status,
        error=quote.error,
        inclusions=[InclusionItem.model_validate(i) for i in quote.inclusions],
        validity_days=quote.validity_days,
        vat_bp=quote.vat_bp,
        total_ht_cents=ht,
        vat_cents=vat,
        total_ttc_cents=ht + vat if ht is not None and vat is not None else None,
        options_total_cents=table.options_cents if table else 0,
        has_pdf=quote.file_id is not None,
        has_docx=quote.docx_file_id is not None,
        stale=stale,
        updated_at=quote.updated_at,
    )


def quote_state(db: Session, bid: Bid) -> QuoteStateOut:
    quote = get_quote(db, bid)
    blocked = blocking(db, bid)
    return QuoteStateOut(
        quote=quote_out(db, bid, quote) if quote is not None else None,
        blocking=blocked[1] if blocked else None,
        cctp=bool(_cctp_pages(db, bid)),
    )


# ---------- preparing (paid when the CCTP is read) ----------------------------------------


def close_stale(db: Session, quote: Quote) -> None:
    """A preparation left for dead: failed, its credit given back (caller commits)."""
    quote.status, quote.error = "error", INTERRUPTED
    set_job_status(db, JOB_DRAFT, quote.id, "error", INTERRUPTED)


def _set_number(db: Session, quote: Quote, number: str | None) -> None:
    """The company's own number (25/11), never one another quote of the company already has
    (its own or Pilao's); empty: back to Pilao's D-AAAA-NNNN."""
    if number is None:
        return
    if number == "" or number == quote.proposed_number:
        quote.custom_number = None
        return
    wanted = number.casefold()
    for other in db.scalars(select(Quote).where(Quote.id != quote.id)):
        # its Pilao number too: it comes back when the other quote's field is emptied
        if wanted in (other.number.casefold(), other.proposed_number.casefold()):
            title = db.get_one(Bid, other.bid_id).title
            taken = other.number if other.number.casefold() == wanted else other.proposed_number
            raise ApiError(
                409,
                "number_taken",
                f"Le numéro {taken} est déjà celui du devis « {title} ».",
            )
    quote.custom_number = number


def _next_seq(db: Session, org_id: uuid.UUID, year: int) -> int:
    top = db.scalar(select(func.max(Quote.seq)).where(Quote.org_id == org_id, Quote.year == year))
    return (top or 0) + 1


def start_quote(
    db: Session,
    user: User,
    bid: Bid,
    summarize: bool,
    queue: JobQueue,
    number: str | None = None,
) -> QuoteOut:
    credits.lock_org(db, bid.org_id)  # a second click waits here; numbers never collide
    blocked = blocking(db, bid)
    if blocked is not None:
        code, message = blocked
        raise ApiError(422 if code == "not_consultation" else 409, code, message)
    quote = get_quote(db, bid)
    if quote is not None and quote.status == "drafting":
        if quote.updated_at >= datetime.now(UTC) - STALE_AFTER:
            return quote_out(db, bid, quote)  # already on its way: never charged twice
        close_stale(db, quote)
    if quote is None:
        year = datetime.now(UTC).astimezone(PARIS).year
        quote = Quote(
            org_id=bid.org_id,
            bid_id=bid.id,
            year=year,
            seq=_next_seq(db, bid.org_id, year),
            inclusions=[],
            created_by=user.id,
        )
        db.add(quote)
    _set_number(db, quote, number)
    found = _sheet(db, bid)
    assert found is not None  # not blocked
    paid = summarize and bool(_pages_to_send(db, bid, quote_table(found[1], found[2])))
    quote.status, quote.error = "drafting", None
    quote.updated_at = datetime.now(UTC)
    db.flush()
    db.add(Job(kind=JOB_DRAFT, ref_id=quote.id, org_id=bid.org_id, status="pending"))
    db.add(
        AuditLog(
            user_id=user.id,
            action="draft_quote",
            entity="quote",
            entity_id=quote.id,
            meta={"number": quote.number, "cctp": paid},
        )
    )
    if paid:
        org = db.get_one(Organization, bid.org_id)
        credits.charge(db, org, TASK, user_id=user.id, bid_id=bid.id, ref_id=quote.id)
    db.commit()
    _enqueue(db, quote, summarize and paid, queue)
    return quote_out(db, bid, quote)


def update_quote(
    db: Session, user: User, bid: Bid, data: QuoteSettingsIn, queue: JobQueue
) -> QuoteOut:
    """New validity, VAT or bullets: the files are made again, for free."""
    credits.lock_org(db, bid.org_id)
    quote = get_quote(db, bid)
    if quote is None:
        raise ApiError(404, "not_found", "Aucun devis pour ce dossier.")
    if quote.status == "drafting" and quote.updated_at >= datetime.now(UTC) - STALE_AFTER:
        raise ApiError(409, "busy", "Le devis est en cours de préparation : réessayez.")
    blocked = blocking(db, bid)
    if blocked is not None:
        raise ApiError(409, blocked[0], blocked[1])
    if data.validity_days is not None:
        quote.validity_days = data.validity_days
    if data.vat_bp is not None:
        quote.vat_bp = data.vat_bp
    if data.inclusions is not None:
        quote.inclusions = [i.model_dump() for i in data.inclusions]  # a new list: saved
    _set_number(db, quote, data.number)
    quote.status, quote.error = "drafting", None
    quote.updated_at = datetime.now(UTC)
    db.add(Job(kind=JOB_DRAFT, ref_id=quote.id, org_id=bid.org_id, status="pending"))
    db.add(
        AuditLog(
            user_id=user.id,
            action="update",
            entity="quote",
            entity_id=quote.id,
            meta=data.model_dump(exclude_none=True, exclude={"inclusions"}),
        )
    )
    db.commit()
    _enqueue(db, quote, False, queue)
    return quote_out(db, bid, quote)


def _enqueue(db: Session, quote: Quote, summarize: bool, queue: JobQueue) -> None:
    try:
        queue.enqueue_draft_quote(quote.id, summarize)
    except Exception:
        logger.exception("could not enqueue quote %s", quote.id)
        _fail(db, quote, QUEUE_DOWN)


def _fail(db: Session, quote: Quote, message: str) -> None:
    quote.status, quote.error = "error", message
    set_job_status(db, JOB_DRAFT, quote.id, "error", message)  # gives the credit back
    db.commit()


def _summarize(db: Session, quote: Quote, bid: Bid, org: Organization, table: QuoteTable) -> None:
    sent = _pages_to_send(db, bid, table)
    if not sent:
        quote.inclusions = []
        return
    rubriques: dict[str, list[str]] = {}
    for r in table.rows:
        rubriques.setdefault(r.section or "Sans rubrique", []).append(f"{r.label} ({r.unit})")
    listed = "\n".join(f"{s} : {', '.join(labels)}" for s, labels in rubriques.items())
    passages = "\n\n".join(f"[{p.file} p.{p.page}]\n{p.text.strip()}" for p in sent)
    prompt = load_prompt(PROMPT)
    system, user_msg = prompt.render(
        company=org.name,
        rubriques=listed.replace("</rubriques", "‹/rubriques"),
        passages=passages.replace("</passages", "‹/passages"),
    )
    result = llm.complete(
        db,
        org_id=org.id,
        task=TASK,
        bid_id=bid.id,
        prompt_version=prompt.version,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
        response_model=InclusionsOut,
        max_tokens=3_000,
    )
    quote.inclusions = keep_sourced(result.data.inclusions, sent)


def _doc_data(
    db: Session,
    quote: Quote,
    bid: Bid,
    org: Organization,
    table: QuoteTable,
    storage: ObjectStorage,
) -> QuoteDocData:
    contact = " — ".join(x for x in (bid.contact_name, bid.contact_email) if x) or None
    return QuoteDocData(
        number=quote.number,
        issued=quote.updated_at.astimezone(PARIS).date(),
        validity_days=quote.validity_days,
        vat_bp=quote.vat_bp,
        company=Company(
            name=org.name,
            legal_form=org.legal_form,
            siret=org.siret,
            address_line=org.address_line,
            postal_code=org.postal_code,
            city=org.city,
            phone=org.phone,
            email=org.contact_email,
            signatory_name=org.signatory_name,
            signatory_role=org.signatory_role,
        ),
        client=bid.buyer_name,
        contact=contact,
        subject=bid.title,
        reference=bid.lot_label or bid.reference,
        inclusions=list(quote.inclusions),
        table=table,
        brand_color=org.brand_color,
        logo=load_logo(db, org, storage),
    )


def run_draft_quote(
    db: Session,
    quote_id: uuid.UUID,
    storage: ObjectStorage,
    converter: PdfConverter,
    summarize: bool,
) -> None:
    quote = db.get(Quote, quote_id)
    if quote is None or quote.status != "drafting":
        return
    scope_session(db, quote.org_id)
    bid = db.get_one(Bid, quote.bid_id)
    org = db.get_one(Organization, quote.org_id)
    set_job_status(db, JOB_DRAFT, quote.id, "running")
    db.commit()
    stored: list[str] = []
    previous = [f for f in (quote.file_id, quote.docx_file_id, quote.zip_file_id) if f]
    try:
        found = _sheet(db, bid)
        if found is None:
            raise ApiError(409, "no_prices", NO_PRICES)
        table = quote_table(found[1], found[2])
        if summarize:
            _summarize(db, quote, bid, org, table)
        quote.updated_at = datetime.now(UTC)  # the quote's date, and newer than its prices
        docx = build_quote(_doc_data(db, quote, bid, org, table, storage)).to_bytes()
        name = f"Devis {quote.number}"
        entries: list[tuple[str, bytes]] = [(f"{name}.docx", docx)]
        word = store_generated(db, org, quote.created_by, docx, name, DOCX_MIME, "docx", storage)
        stored.append(word.storage_key)
        pdf_record: File | None = None
        try:
            pdf = converter.convert(docx)
        except PdfUnavailable as exc:
            logger.warning("quote %s: no PDF (%s)", quote.id, exc)
        else:
            pdf_record = store_generated(
                db, org, quote.created_by, pdf, name, PDF_MIME, "pdf", storage
            )
            stored.append(pdf_record.storage_key)
            entries.append((f"{name}.pdf", pdf))
        filled, filled_name = pricing_svc.filled_file(db, found[0], storage)
        suffix = "" if found[0].mode == "document" else " - rempli"  # a DPGF Pilao wrote
        entries.append((f"{filled_name}{suffix}.xlsx", filled))
        bundle = store_generated(
            db, org, quote.created_by, _zip(entries), name, ZIP_MIME, "zip", storage
        )
        stored.append(bundle.storage_key)
        quote.docx_file_id, quote.zip_file_id = word.id, bundle.id
        quote.priced_hash = fingerprint(table)
        quote.file_id = pdf_record.id if pdf_record else None
        quote.status, quote.error = "ready", None
        set_job_status(db, JOB_DRAFT, quote.id, "done")
        db.commit()
    except Exception as exc:
        db.rollback()
        for key in stored:
            discard_object(storage, key)
        if isinstance(exc, llm.LlmProviderError):
            message = PROVIDER_DOWN
        elif isinstance(exc, llm.LlmError):
            message = str(exc)
        elif isinstance(exc, ApiError):
            message = exc.message
        else:
            logger.exception("quote %s failed", quote_id)
            message = FAILED
        _fail(db, db.get_one(Quote, quote_id), message)
        return
    for file_id in previous:
        record = db.get(File, file_id)
        if record is not None:
            delete_file(db, None, record, storage)


def _zip(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry_name, data in entries:
            zf.writestr(entry_name, data)
    return buf.getvalue()


# ---------- downloads ----------------------------------------------------------------------


def download(db: Session, bid: Bid, fmt: str, storage: ObjectStorage) -> DownloadUrlOut:
    quote = get_quote(db, bid)
    if quote is None or quote.status != "ready":
        raise ApiError(409, "not_ready", NOT_READY)
    file_id = {"pdf": quote.file_id, "docx": quote.docx_file_id, "zip": quote.zip_file_id}[fmt]
    record = db.get(File, file_id) if file_id else None
    if record is None:
        raise ApiError(409, "no_pdf", NO_PDF)
    ttl = get_settings().signed_url_ttl_seconds
    url = storage.signed_download_url(record.storage_key, record.filename, ttl)
    return DownloadUrlOut(url=url, expires_in=ttl)
