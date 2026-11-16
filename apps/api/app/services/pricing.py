"""Chiffrage (ADR-049): read the buyer's price file, take the company's hours, fill the file.

« Lire le fichier » (paid, in the background): the AI lists the lines to price, the server
keeps what the file confirms. The company then types hours or prices; Pilao computes with its
rates and hands back the buyer's own file, filled cell by cell. The hours also feed the memoir.
"""

import logging
import re
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
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
    DceVersion,
    File,
    Job,
    Organization,
    PriceSheet,
    PricingRates,
    User,
)
from app.documents.convert import ConversionUnavailable, soffice_convert
from app.domain.price_grid import PriceFileError, grid_text, read_workbook
from app.domain.pricing import (
    LineIn,
    Priced,
    PriceLine,
    PriceReadOut,
    Rates,
    broken_links,
    compute,
    fill_writes,
    hours_summary,
    parse_hours,
    validate_lines,
)
from app.exports.xlsx_fill import XlsxFillError, fill_xlsx
from app.schemas.files import DownloadUrlOut
from app.schemas.pricing import (
    PriceFileOut,
    PriceLineOut,
    PriceSheetOut,
    PricesOut,
    RatesIn,
    RatesOut,
    SheetUpdateIn,
)
from app.services import credits
from app.services.dce_analysis import PRICE_KINDS
from app.services.files import delete_file, discard_object, store_generated
from app.services.jobs import set_job_status
from app.storage.objects import ObjectStorage
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.pricing")

JOB_READ = "read_prices"
TASK = "price_read"
PROMPT = "lecture_bordereau_prix"
MAX_OUTPUT_TOKENS = 32_000  # a 300-line DPGF answers with short lines (cells only)
STALE_AFTER = timedelta(minutes=15)  # past the queue's timeout (600 s): the reading is dead
FILLABLE = ("xlsx", "xlsm")
CONVERTIBLE = ("xls", "ods")
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

QUEUE_DOWN = "File d'attente indisponible : réessayez."
PROVIDER_DOWN = "Service d'IA indisponible : réessayez."
FAILED = "La lecture du fichier de prix n'a pas abouti : réessayez."
INTERRUPTED = "La lecture du fichier de prix a été interrompue : réessayez."
NO_LINES = "Pilao n'a trouvé aucune ligne à chiffrer dans ce fichier."
NOT_FILLABLE = (
    "Pilao ne peut remplir qu'un fichier Excel (.xlsx, .xls) ou Calc (.ods). "
    "Demandez la version Excel du bordereau à l'acheteur."
)
NOT_READY = "Lisez d'abord le fichier de prix."


def _ext(path: str) -> str:
    return path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""


def _stem(path: str) -> str:
    name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def fillable(path: str) -> bool:
    return _ext(path) in FILLABLE + CONVERTIBLE


# ---------- the company's rates -------------------------------------------------------------


def rates_row(db: Session, org_id: uuid.UUID) -> PricingRates | None:
    return db.scalar(select(PricingRates).where(PricingRates.org_id == org_id))


def rates_of(db: Session, org_id: uuid.UUID) -> Rates:
    row = rates_row(db, org_id)
    if row is None:
        return Rates(None, None, None, None)
    return Rates(row.hourly_rate_cents, row.night_pct, row.sunday_pct, row.holiday_pct)


def rates_out(db: Session, org_id: uuid.UUID) -> RatesOut:
    r = rates_of(db, org_id)
    return RatesOut(
        hourly_rate_cents=r.hourly_rate_cents,
        night_pct=r.night_pct,
        sunday_pct=r.sunday_pct,
        holiday_pct=r.holiday_pct,
    )


def save_rates(db: Session, user: User, org_id: uuid.UUID, data: RatesIn) -> RatesOut:
    row = rates_row(db, org_id)
    if row is None:
        row = PricingRates(org_id=org_id)
        db.add(row)
    row.hourly_rate_cents = data.hourly_rate_cents
    row.night_pct, row.sunday_pct, row.holiday_pct = (
        data.night_pct,
        data.sunday_pct,
        data.holiday_pct,
    )
    db.add(AuditLog(user_id=user.id, action="update_rates", entity="pricing_rates", meta={}))
    db.commit()
    return rates_out(db, org_id)


# ---------- the price files of a dossier ----------------------------------------------------


def price_files(db: Session, bid: Bid) -> list[DceFile]:
    """The BPU / DPGF / DQE of the latest processed DCE."""
    version = db.scalars(
        select(DceVersion)
        .where(DceVersion.bid_id == bid.id, DceVersion.status == "ready")
        .order_by(DceVersion.version.desc())
    ).first()
    if version is None:
        return []
    return list(
        db.scalars(
            select(DceFile)
            .where(DceFile.dce_version_id == version.id, DceFile.detected_kind.in_(PRICE_KINDS))
            .order_by(DceFile.path)
        )
    )


def _lines(sheet: PriceSheet) -> list[PriceLine]:
    return [PriceLine.from_dict(d) for d in sheet.lines]


def _priced(db: Session, sheet: PriceSheet) -> tuple[list[PriceLine], Priced]:
    lines = _lines(sheet)
    return lines, compute(lines, sheet.entries, rates_of(db, sheet.org_id), sheet.rate_cents)


def sheet_out(db: Session, sheet: PriceSheet) -> PriceSheetOut:
    lines, priced = _priced(db, sheet)
    by_id = {p.id: p for p in priced.lines}
    return PriceSheetOut(
        id=sheet.id,
        status=sheet.status,
        error=sheet.error,
        warnings=sheet.warnings,
        notes=sheet.notes,
        rate_cents=sheet.rate_cents,
        lines=[
            PriceLineOut(
                id=ln.id,
                section=ln.section,
                label=ln.label,
                unit=ln.unit,
                quantity=None if ln.quantity is None else format(ln.quantity.normalize(), "f"),
                hourly=ln.hourly,
                surcharge=ln.surcharge,
                hours=None if by_id[ln.id].hours is None else str(sheet.entries[ln.id]["hours"]),
                price_cents=by_id[ln.id].price_cents,
                total_cents=by_id[ln.id].total_cents,
                source=by_id[ln.id].source,
            )
            for ln in lines
        ],
        total_cents=priced.total_cents,
        missing_count=priced.missing_count,
    )


def prices_for_bid(db: Session, bid: Bid) -> PricesOut:
    files = price_files(db, bid)
    sheets = {
        s.dce_file_id: s
        for s in db.scalars(
            select(PriceSheet).where(
                PriceSheet.bid_id == bid.id, PriceSheet.dce_file_id.in_([f.id for f in files])
            )
        )
    }
    excel_stems = {_stem(f.path) for f in files if fillable(f.path)}
    out = []
    for f in files:
        if not fillable(f.path) and _stem(f.path) in excel_stems:
            continue  # the PDF twin of an Excel file: the Excel one is filled
        sheet = sheets.get(f.id)
        out.append(
            PriceFileOut(
                dce_file_id=f.id,
                path=f.path,
                kind=f.detected_kind,
                fillable=fillable(f.path),
                sheet=sheet_out(db, sheet) if sheet is not None else None,
            )
        )
    return PricesOut(rates=rates_out(db, bid.org_id), files=out)


# ---------- reading (paid, in the background) -----------------------------------------------


def close_stale(db: Session, sheet: PriceSheet) -> None:
    """A reading left for dead: failed, its credit given back (caller commits)."""
    sheet.status, sheet.error = "error", INTERRUPTED
    set_job_status(db, JOB_READ, sheet.id, "error", INTERRUPTED)


def start_read(
    db: Session, user: User, bid: Bid, dce_file_id: uuid.UUID, queue: JobQueue
) -> PriceSheet:
    credits.lock_org(db, bid.org_id)  # a second click waits here, then finds the first one
    dce_file = next((f for f in price_files(db, bid) if f.id == dce_file_id), None)
    if dce_file is None:
        raise ApiError(404, "not_found", "Fichier de prix introuvable.")
    if not fillable(dce_file.path):
        raise ApiError(422, "not_fillable", NOT_FILLABLE)
    sheet = db.scalar(select(PriceSheet).where(PriceSheet.dce_file_id == dce_file.id))
    if sheet is not None and sheet.status == "reading":
        if sheet.updated_at >= datetime.now(UTC) - STALE_AFTER:
            return sheet  # already on its way: never charged twice
        close_stale(db, sheet)
    if sheet is None:
        sheet = PriceSheet(org_id=bid.org_id, bid_id=bid.id, dce_file_id=dce_file.id)
        db.add(sheet)
    sheet.status, sheet.error, sheet.created_by = "reading", None, user.id
    db.flush()
    db.add(Job(kind=JOB_READ, ref_id=sheet.id, org_id=bid.org_id, status="pending"))
    db.add(
        AuditLog(
            user_id=user.id,
            action="read_prices",
            entity="price_sheet",
            entity_id=sheet.id,
            meta={"file": dce_file.path},
        )
    )
    credits.charge(
        db,
        db.get_one(Organization, bid.org_id),
        "price_read",
        user_id=user.id,
        bid_id=bid.id,
        ref_id=sheet.id,
    )
    db.commit()
    try:
        queue.enqueue_read_prices(sheet.id)
    except Exception:
        logger.exception("could not enqueue price reading %s", sheet.id)
        _fail(db, sheet, QUEUE_DOWN)
    return sheet


def _fail(db: Session, sheet: PriceSheet, message: str) -> None:
    sheet.status, sheet.error = "error", message
    set_job_status(db, JOB_READ, sheet.id, "error", message)  # gives the credit back
    db.commit()


def _source_bytes(
    db: Session, sheet: PriceSheet, dce_file: DceFile, storage: ObjectStorage
) -> tuple[bytes, bool]:
    """The .xlsx to read and fill: the buyer's, or its conversion (stored once)."""
    if sheet.source_file_id is not None:
        source = db.get(File, sheet.source_file_id)
        if source is not None:
            return storage.get(source.storage_key).read(), _ext(dce_file.path) in CONVERTIBLE
    original = db.get_one(File, dce_file.file_id)
    data = storage.get(original.storage_key).read()
    ext = _ext(dce_file.path)
    if ext in FILLABLE:
        sheet.source_file_id = original.id
        return data, False
    converted = soffice_convert(data, ext, "xlsx", get_settings().pdf_timeout_seconds)
    name = dce_file.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    record = store_generated(
        db,
        db.get_one(Organization, sheet.org_id),
        None,
        converted,
        name,
        XLSX_MIME,
        "xlsx",
        storage,
    )
    sheet.source_file_id = record.id
    return converted, True


def _line_key(line: dict[str, Any]) -> str:
    """Two price files of a dossier describe the same line with the same section and label
    (Rillieux: the BPM and the DQE); the key ignores case, accents and spacing."""
    text = f"{line.get('section') or ''}|{line.get('label') or ''}"
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", plain).strip()


def _siblings(db: Session, sheet: PriceSheet, lock: bool = False) -> list[PriceSheet]:
    query = select(PriceSheet).where(
        PriceSheet.bid_id == sheet.bid_id, PriceSheet.id != sheet.id, PriceSheet.status == "ready"
    )
    return list(db.scalars(query.with_for_update() if lock else query))


def _file_name(db: Session, sheet: PriceSheet) -> str:
    return db.get_one(DceFile, sheet.dce_file_id).path.rsplit("/", 1)[-1]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n > 1 else ''}"


def run_read_prices(db: Session, sheet_id: uuid.UUID, storage: ObjectStorage) -> None:
    sheet = db.get(PriceSheet, sheet_id)
    if sheet is None or sheet.status != "reading":
        return
    scope_session(db, sheet.org_id)
    set_job_status(db, JOB_READ, sheet.id, "running")
    sheet.updated_at = datetime.now(UTC)
    db.commit()
    dce_file = db.get_one(DceFile, sheet.dce_file_id)
    try:
        data, converted = _source_bytes(db, sheet, dce_file, storage)
        sheets = read_workbook(data)
        filled = [s for s in sheets if not s.hidden and s.cells]
        if not filled:
            raise PriceFileError("Ce fichier ne contient aucune case remplie.")
        prompt = load_prompt(PROMPT)
        proposed: list[LineIn] = []
        notes: list[str] = []
        cut = False
        for part in filled:  # one call per sheet: a DPGF often has one sheet per lot
            grid, part_cut = grid_text([part])
            cut = cut or part_cut
            system, user_msg = prompt.render(
                file_name=dce_file.path.replace("<", "‹"),
                grid=grid.replace("</grid", "‹/grid"),
            )
            result = llm.complete(
                db,
                org_id=sheet.org_id,
                task=TASK,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                response_model=PriceReadOut,
                prompt_version=prompt.version,
                bid_id=sheet.bid_id,
                max_tokens=MAX_OUTPUT_TOKENS,
            )
            proposed.extend(result.data.lines)
            notes.extend(n for n in result.data.notes if n not in notes)
        lines, warnings = validate_lines(proposed, sheets)
        if not lines:
            _fail(db, sheet, NO_LINES)
            return
        mirrors = broken_links(lines, sheets)
        labels = {ln.id: ln for ln in lines}
        for line_id, cells in mirrors.items():
            ln = labels[line_id]
            where = f"{ln.section} · {ln.label}" if ln.section else ln.label
            warnings.append(
                f"« {where} » : dans le fichier de l'acheteur, la case {', '.join(cells)} ne "
                "reprenait pas le prix (valeur fixe). Pilao y écrira aussi le prix."
            )
        if cut:
            warnings.append(
                "Fichier très grand : seule sa première partie a été lue. Vérifiez qu'aucune "
                "ligne ne manque."
            )
        if converted:
            warnings.append(
                "Le fichier de l'acheteur a été converti au format .xlsx : le fichier rempli "
                "sera un .xlsx. Vérifiez sa mise en page avant de le déposer."
            )
        sheet.lines = [ln.to_dict() for ln in lines]
        sheet.mirrors = mirrors
        sheet.notes = [re.sub(r"\s+", " ", n).strip()[:300] for n in notes[:5]]
        entries = {k: v for k, v in sheet.entries.items() if k in labels}
        by_key = {_line_key(d): d["id"] for d in sheet.lines}
        for other in _siblings(db, sheet):
            copied = 0
            for line in other.lines:
                target = by_key.get(_line_key(line))
                entry = other.entries.get(line["id"])
                if target and entry and target not in entries:
                    entries[target] = dict(entry)
                    copied += 1
            if copied:
                warnings.append(
                    f"Heures et prix repris de « {_file_name(db, other)} » pour "
                    f"{_plural(copied, 'ligne')} identique{'s' if copied > 1 else ''}."
                )
        sheet.entries = entries  # a new object: an in-place change of JSONB is not saved
        sheet.warnings = list(warnings)
        sheet.status, sheet.error = "ready", None
        set_job_status(db, JOB_READ, sheet.id, "done")
        db.commit()
    except llm.LlmProviderError:
        db.rollback()
        _fail(db, sheet, PROVIDER_DOWN)
    except llm.LlmError:
        db.rollback()
        _fail(db, sheet, FAILED)
    except PriceFileError as exc:
        db.rollback()
        _fail(db, sheet, str(exc))
    except ConversionUnavailable:
        db.rollback()
        _fail(db, sheet, "La conversion du fichier en .xlsx n'a pas abouti : réessayez.")
    except Exception:
        logger.exception("price reading %s failed", sheet_id)
        db.rollback()
        _fail(db, sheet, FAILED)


# ---------- what the company types ----------------------------------------------------------


def get_sheet(db: Session, sheet_id: uuid.UUID) -> PriceSheet:
    sheet = db.get(PriceSheet, sheet_id)
    if sheet is None:
        raise ApiError(404, "not_found", "Fichier de prix introuvable.")
    return sheet


def update_sheet(db: Session, user: User, sheet: PriceSheet, data: SheetUpdateIn) -> PriceSheetOut:
    locked = db.get_one(PriceSheet, sheet.id, with_for_update=True, populate_existing=True)
    if locked.status != "ready":
        raise ApiError(409, "not_ready", NOT_READY)
    known = {d["id"] for d in locked.lines}
    entries: dict[str, dict[str, Any]] = dict(locked.entries)
    for line_id, entry in data.entries.items():
        if line_id not in known:
            raise ApiError(422, "unknown_line", "Cette ligne n'existe plus : rechargez la page.")
        value: dict[str, Any] = {}
        if entry.hours is not None and entry.hours.strip():
            if parse_hours(entry.hours) is None:
                raise ApiError(422, "bad_hours", "Nombre d'heures invalide.")
            value["hours"] = entry.hours.strip().replace(",", ".")
        if entry.price_cents is not None:
            value["price_cents"] = entry.price_cents
        if value:
            entries[line_id] = value
        else:
            entries.pop(line_id, None)
    locked.entries = entries
    keys = {d["id"]: _line_key(d) for d in locked.lines}
    changed = {keys[i]: entries.get(i) for i in data.entries}
    for other in _siblings(db, locked, lock=True):
        synced = dict(other.entries)
        for line in other.lines:
            key = _line_key(line)
            if key in changed:
                if changed[key]:
                    synced[line["id"]] = dict(changed[key])  # type: ignore[arg-type]
                else:
                    synced.pop(line["id"], None)
        other.entries = synced
    if data.set_rate:
        locked.rate_cents = data.rate_cents
    db.add(
        AuditLog(
            user_id=user.id,
            action="update_prices",
            entity="price_sheet",
            entity_id=locked.id,
            meta={"lines": len(data.entries)},
        )
    )
    db.commit()
    return sheet_out(db, locked)


def export_filled(
    db: Session, org: Organization, user: User, sheet: PriceSheet, storage: ObjectStorage
) -> DownloadUrlOut:
    """The buyer's file with the company's prices, as a short-lived download link."""
    if sheet.status != "ready":
        raise ApiError(409, "not_ready", NOT_READY)
    dce_file = db.get_one(DceFile, sheet.dce_file_id)
    data, _ = _source_bytes(db, sheet, dce_file, storage)
    lines, priced = _priced(db, sheet)
    try:
        filled = fill_xlsx(data, fill_writes(lines, priced, sheet.mirrors))
    except XlsxFillError as exc:
        raise ApiError(422, "fill_failed", f"Le fichier n'a pas pu être rempli : {exc}") from exc
    name = dce_file.path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    record = store_generated(
        db, org, user.id, filled, f"{name} - rempli", XLSX_MIME, "xlsx", storage
    )
    previous = db.get(File, sheet.filled_file_id) if sheet.filled_file_id else None
    sheet.filled_file_id = record.id
    try:
        db.commit()
    except Exception:
        discard_object(storage, record.storage_key)
        raise
    if previous is not None:
        delete_file(db, user, previous, storage)
    ttl = get_settings().signed_url_ttl_seconds
    return DownloadUrlOut(
        url=storage.signed_download_url(record.storage_key, record.filename, ttl), expires_in=ttl
    )


# ---------- for the memoir ------------------------------------------------------------------


def bid_hours(db: Session, bid: Bid) -> dict[str, Any] | None:
    """The hours the company typed in this dossier's price files (never a price)."""
    rows: list[dict[str, Any]] = []
    total = 0.0
    for sheet in db.scalars(
        select(PriceSheet)
        .where(PriceSheet.bid_id == bid.id, PriceSheet.status == "ready")
        .order_by(PriceSheet.created_at)
    ):
        lines, priced = _priced(db, sheet)
        summary = hours_summary(lines, priced)
        if summary is not None:
            rows.extend(summary["lignes"])
            total += float(summary["heures_totales"])
    if not rows:
        return None
    return {"lignes": rows, "heures_totales": format(total, "g")}
