"""GDPR rights of an organization (docs/09, ADR-026): full export, and erasure.

* **Export**: a ZIP with every row of the organization (all tables that carry its
  ``org_id``, without secrets: password and token hashes, embeddings), the notices it
  matched, and every file it deposited, in its original form.
* **Erasure**: requested by an administrator who types the company name, carried out after
  ``DELETION_GRACE_DAYS`` (cancellable until then). The purge deletes the stored objects
  first, then the organization row: every table cascades on ``org_id`` (vector index
  included). Only a receipt without personal data remains (``purge_logs``).
"""

import json
import logging
import shutil
import tempfile
import uuid
import zipfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import Email, Mailer, send_quietly
from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.base import Base
from app.db.models import (
    AuditLog,
    DataRequest,
    File,
    Organization,
    PurgeLog,
    TenderMatch,
    User,
)
from app.exports.bundle import safe_name
from app.exports.dc_forms import french_date
from app.services.files import discard_object, store_generated_file
from app.storage.objects import ObjectStorage
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.org_data")
EXCLUDED_TABLES = {"auth_tokens", "user_sessions"}  # one-shot secrets, no value for the owner
EXCLUDED_COLUMNS = {
    "password_hash",
    "token_hash",
    "embedding",
    "embedding_text_hash",
    "content_hash",
}
ZIP_MIME = "application/zip"


def _now() -> datetime:
    return datetime.now(UTC)


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes | memoryview):
        return None
    raise TypeError(type(value).__name__)


def _org_tables() -> list[Any]:
    return [
        t
        for t in Base.metadata.sorted_tables
        if "org_id" in t.c and t.name not in EXCLUDED_TABLES and t.name != "purge_logs"
    ]


def export_rows(db: Session, org_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    """Every row of the organization, table by table (explicit ``org_id`` filter)."""
    out: dict[str, list[dict[str, Any]]] = {}
    orgs = Base.metadata.tables["organizations"]
    out["organizations"] = [
        dict(r._mapping) for r in db.execute(select(orgs).where(orgs.c.id == org_id))
    ]
    for table in _org_tables():
        columns = [c for c in table.c if c.name not in EXCLUDED_COLUMNS]
        out[table.name] = [
            dict(r._mapping) for r in db.execute(select(*columns).where(table.c.org_id == org_id))
        ]
    tenders = Base.metadata.tables["tenders"]
    matched = select(TenderMatch.tender_id).where(TenderMatch.org_id == org_id)
    out["tenders"] = [  # public notices, so the export reads on its own
        dict(r._mapping)
        for r in db.execute(
            select(*[c for c in tenders.c if c.name != "raw"]).where(tenders.c.id.in_(matched))
        )
    ]
    return out


# ---------- export --------------------------------------------------------------------


def request_export(db: Session, user: User, queue: JobQueue) -> DataRequest:
    running = db.scalar(
        select(DataRequest.id).where(
            DataRequest.kind == "export",
            DataRequest.status == "pending",
            DataRequest.created_at > _now() - timedelta(hours=1),
        )
    )
    if running is not None:
        raise ApiError(409, "export_running", "Un export est déjà en préparation.")
    req = DataRequest(id=uuid.uuid4(), org_id=user.org_id, kind="export", requested_by=user.id)
    db.add(req)
    db.add(AuditLog(user_id=user.id, action="export", entity="organization", entity_id=user.org_id))
    db.commit()
    try:
        queue.enqueue_org_export(req.id)
    except Exception:
        logger.exception("could not enqueue the export %s", req.id)
        req.status, req.error = "error", "File d'attente indisponible : relancez l'export."
        db.commit()
    return req


README = """Export des données de {name} — {when}

donnees.json   toutes les données de l'entreprise dans Pilao, table par table : profil,
               références, moyens, attestations, dossiers, analyses des DCE, mémoires et
               leurs versions, documents générés, annonces suivies, journal d'activité.
               Les mots de passe et jetons de connexion n'y figurent pas (ils sont chiffrés
               de façon irréversible) ; les index de recherche non plus (recalculables).
fichiers/      chaque fichier déposé ou produit, sous sa forme d'origine, préfixé par son
               identifiant (colonne « id » de la table « files » dans donnees.json).

Les dates sont en UTC (format ISO 8601), les montants en centimes d'euro HT.
"""


def run_org_export(db: Session, request_id: uuid.UUID, storage: ObjectStorage) -> None:
    req = db.get(DataRequest, request_id)
    if req is None or req.kind != "export":
        return
    org_id = req.org_id
    scope_session(db, org_id)
    org = db.get_one(Organization, org_id)
    data = export_rows(db, org_id)
    previous_exports = set(
        db.scalars(
            select(DataRequest.file_id).where(
                DataRequest.kind == "export", DataRequest.file_id.is_not(None)
            )
        )
    )
    files = [
        f
        for f in db.scalars(select(File).order_by(File.created_at))
        if f.id not in previous_exports
    ]
    with tempfile.TemporaryFile() as tmp:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            zf.writestr(
                "LISEZ-MOI.txt",
                README.format(name=org.name, when=french_date(_now().date())).replace("\n", "\r\n"),
            )
            zf.writestr(
                "donnees.json",
                json.dumps(data, ensure_ascii=False, indent=1, default=_jsonable),
            )
            for record in files:
                with zf.open(f"fichiers/{record.id}-{safe_name(record.filename)}", "w") as dst:
                    shutil.copyfileobj(storage.get(record.storage_key), dst, 1024 * 1024)
        size = tmp.tell()
        tmp.seek(0)
        stamp = _now().strftime("%Y-%m-%d")
        record = store_generated_file(
            db,
            org,
            req.requested_by,
            tmp,
            size,
            f"Export Pilao - {org.name[:80]} - {stamp}.zip",
            ZIP_MIME,
            "zip",
            storage,
            check_quota=False,  # the owner's right: never refused for lack of space
        )
    old = db.scalars(
        select(DataRequest).where(
            DataRequest.kind == "export",
            DataRequest.id != req.id,
            DataRequest.file_id.is_not(None),
        )
    ).all()
    keys = []
    for previous in old:  # keep only the latest export file
        stale = db.get(File, previous.file_id)
        if stale is not None:
            keys.append(stale.storage_key)
            db.delete(stale)
    req.file_id, req.status, req.error = record.id, "ready", None
    try:
        db.commit()
    except Exception:
        db.rollback()
        discard_object(storage, record.storage_key)
        raise
    for key in keys:
        discard_object(storage, key)


# ---------- erasure -------------------------------------------------------------------


def _recipients(db: Session, org_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(User.email).where(User.org_id == org_id, User.email_verified_at.is_not(None))
        )
    )


def pending_deletion(db: Session) -> DataRequest | None:
    return db.scalar(
        select(DataRequest).where(DataRequest.kind == "deletion", DataRequest.status == "pending")
    )


def request_deletion(
    db: Session, user: User, org: Organization, confirmation: str, mailer: Mailer
) -> DataRequest:
    if confirmation.strip().casefold() != org.name.strip().casefold():
        raise ApiError(
            422,
            "confirmation_mismatch",
            "Recopiez exactement le nom de l'entreprise pour confirmer.",
        )
    if pending_deletion(db) is not None:
        raise ApiError(409, "deletion_pending", "La suppression est déjà programmée.")
    due = _now() + timedelta(days=get_settings().deletion_grace_days)
    req = DataRequest(
        id=uuid.uuid4(), org_id=org.id, kind="deletion", requested_by=user.id, due_at=due
    )
    db.add(req)
    db.add(
        AuditLog(
            user_id=user.id, action="request_deletion", entity="organization", entity_id=org.id
        )
    )
    db.commit()
    when = french_date(due.date())
    for email in _recipients(db, org.id):
        send_quietly(
            mailer,
            Email(
                to=email,
                subject=f"Suppression des données de {org.name} programmée le {when}",
                body=(
                    f"Bonjour,\n\n{user.full_name or user.email} a demandé la suppression de toutes "
                    f"les données de {org.name} dans Pilao. Elle aura lieu le {when} : comptes, "
                    "profil, dossiers, mémoires, attestations et fichiers seront effacés "
                    "définitivement.\n\nD'ici là, un administrateur peut l'annuler dans Profil > "
                    "Vos données, et y télécharger un export complet.\n"
                ),
            ),
        )
    return req


def cancel_deletion(db: Session, user: User, org: Organization, mailer: Mailer) -> None:
    req = pending_deletion(db)
    if req is None:
        raise ApiError(404, "not_found", "Aucune suppression programmée.")
    req.status = "cancelled"
    db.add(
        AuditLog(user_id=user.id, action="cancel_deletion", entity="organization", entity_id=org.id)
    )
    db.commit()
    for email in _recipients(db, org.id):
        send_quietly(
            mailer,
            Email(
                to=email,
                subject=f"Suppression des données de {org.name} annulée",
                body=f"Bonjour,\n\n{user.full_name or user.email} a annulé la suppression des "
                f"données de {org.name}. Rien n'a été effacé.\n",
            ),
        )


def purge_due(
    db: Session, storage: ObjectStorage, mailer: Mailer, now: datetime | None = None
) -> int:
    """Hourly (unscoped session): erase the organizations whose deletion date has come."""
    now = now or _now()
    due = db.scalars(
        select(DataRequest).where(
            DataRequest.kind == "deletion",
            DataRequest.status == "pending",
            DataRequest.due_at <= now,
        )
    ).all()
    return sum(_purge(db, req, storage, mailer) for req in due)


def _purge(db: Session, req: DataRequest, storage: ObjectStorage, mailer: Mailer) -> bool:
    org_id, requested_at = req.org_id, req.created_at
    org = db.get(Organization, org_id)
    if org is None:
        return False
    keys = list(db.scalars(select(File.storage_key).where(File.org_id == org_id)))
    for key in keys:  # objects first: a failure leaves everything in place, retried next hour
        try:
            storage.delete(key)
        except Exception:
            logger.exception("purge of %s: could not delete object %s", org_id, key)
            req.error = "Suppression des fichiers interrompue : nouvelle tentative dans une heure."
            db.commit()
            return False
    counts = {
        t.name: n
        for t in _org_tables()
        if (n := db.scalar(select(func.count()).select_from(t).where(t.c.org_id == org_id)))
    }
    name, recipients = org.name, _recipients(db, org_id)
    db.add(PurgeLog(org_id=org_id, requested_at=requested_at, rows=counts, objects=len(keys)))
    db.execute(delete(Organization).where(Organization.id == org_id))  # every table cascades
    db.commit()
    logger.info(
        "organization %s erased: %s rows, %s objects", org_id, sum(counts.values()), len(keys)
    )
    for email in recipients:  # the last message; the addresses are not kept
        send_quietly(
            mailer,
            Email(
                to=email,
                subject=f"Les données de {name} ont été supprimées",
                body=f"Bonjour,\n\nComme demandé, toutes les données de {name} ont été "
                "supprimées de Pilao, fichiers compris. Ce message est le dernier.\n",
            ),
        )
    return True
