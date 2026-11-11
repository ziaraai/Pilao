"""Daily e-mails (P3-05): new notices above the company's threshold (US-2.4) and the
attestations about to expire (US-5.2).

The job runs every hour (``app/workers/cron.py``) and decides by itself: the digest goes
out once per Paris day, in the morning; each expiry alert once per document, deadline and
threshold. ``notifications`` remembers what was sent, so a run repeated or interrupted
never e-mails twice.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import Mailer
from app.db.models import (
    CompanyProfile,
    ComplianceDocument,
    Organization,
    Tender,
    TenderMatch,
)
from app.exports.dc_forms import PROOF_LABELS, french_date
from app.services.org_data import purge_due
from app.services.retention import RetentionReport, purge_expired
from app.services.tenders import notify
from app.services.vault import refresh_stored_statuses
from app.storage.objects import ObjectStorage

logger = logging.getLogger("pilao.alerts")
PARIS = ZoneInfo("Europe/Paris")
DIGEST_WINDOW = (time(7, 0), time(12, 0))  # « chaque matin », Paris time
DEFAULT_THRESHOLD = 60
EXPIRED_ALERT_DAYS = 30  # an attestation expired longer ago is not announced any more


@dataclass
class AlertReport:
    digests: int = 0
    expiry_alerts: int = 0
    statuses_refreshed: int = 0
    organizations_erased: int = 0
    retention: RetentionReport = field(default_factory=RetentionReport)


def _paris(now: datetime) -> datetime:
    return now.astimezone(PARIS)


def send_digests(db: Session, mailer: Mailer, now: datetime) -> int:
    """US-2.4: one e-mail per company and Paris day, with its new notices ≥ its threshold."""
    local = _paris(now)
    if not (DIGEST_WINDOW[0] <= local.time() < DIGEST_WINDOW[1]):
        return 0
    base = get_settings().app_base_url.rstrip("/")
    sent = 0
    for profile in db.scalars(
        select(CompanyProfile)
        .join(Organization, Organization.id == CompanyProfile.org_id)
        .where(Organization.suspended_at.is_(None))  # nothing leaves for a suspended company
    ):
        threshold = (
            profile.min_score_alert if profile.min_score_alert is not None else DEFAULT_THRESHOLD
        )
        rows = db.execute(
            select(TenderMatch, Tender)
            .join(Tender, Tender.id == TenderMatch.tender_id)
            .where(
                TenderMatch.org_id == profile.org_id,
                TenderMatch.status == "new",
                TenderMatch.digested_at.is_(None),
                TenderMatch.score.is_not(None),
                or_(Tender.deadline_at.is_(None), Tender.deadline_at > now),
            )
            .order_by(TenderMatch.score.desc(), Tender.deadline_at.asc().nulls_last())
        ).all()
        if not rows:
            continue
        chosen = [(m, t) for m, t in rows if (m.score or 0) >= threshold]
        if chosen:
            lines = [
                f"- {m.score}/100 — {t.title}\n"
                f"  {t.buyer_name or 'Acheteur non précisé'}"
                + (
                    f" · date limite le {french_date(_paris(t.deadline_at).date())}"
                    if t.deadline_at
                    else ""
                )
                + (f"\n  {m.explanation}" if m.explanation else "")
                for m, t in chosen[:20]
            ]
            more = f"\n… et {len(chosen) - 20} autre(s).\n" if len(chosen) > 20 else ""
            count = len(chosen)
            if not notify(
                db,
                mailer,
                profile.org_id,
                "digest",
                local.date().isoformat(),
                f"Pilao — {count} nouvelle{'s' if count > 1 else ''} annonce{'s' if count > 1 else ''} pour vous",
                f"Bonjour,\n\n{count} nouvelle(s) annonce(s) correspondent à votre profil "
                f"(score de {threshold} ou plus) :\n\n"
                + "\n\n".join(lines)
                + more
                + f"\n\nToutes vos annonces : {base}/annonces\n\n"
                "Le seuil de cet e-mail se règle dans Profil > Paramètres de veille.",
            ):
                continue  # already sent today: those matches wait for tomorrow
            sent += 1
        for match, _ in rows:  # every scored notice was considered once
            match.digested_at = now
        db.commit()
    return sent


def send_expiry_alerts(db: Session, mailer: Mailer, today: date) -> int:
    """US-5.2: e-mail at 30 and 7 days before the end of validity, and once expired."""
    base = get_settings().app_base_url.rstrip("/")
    orgs = {o.id: o for o in db.scalars(select(Organization))}
    sent = 0
    for doc in db.scalars(
        select(ComplianceDocument).where(
            ComplianceDocument.confirmed_at.is_not(None),
            ComplianceDocument.valid_until.is_not(None),
        )
    ):
        assert doc.valid_until is not None
        if orgs[doc.org_id].suspended_at is not None:
            continue  # nothing leaves for a suspended company
        days = (doc.valid_until - today).days
        if days > 30 or days < -EXPIRED_ALERT_DAYS:
            continue  # too early, or expired long before (no e-mail about old history)
        threshold = "expired" if days < 0 else "7" if days <= 7 else "30"
        label = PROOF_LABELS.get(doc.kind, doc.kind)
        when = french_date(doc.valid_until)
        subject = (
            f"Attestation expirée : {label}"
            if days < 0
            else f"Attestation à renouveler : {label} (fin le {when})"
        )
        body = (
            f"Bonjour,\n\n{label} "
            + (
                f"a expiré le {when} : elle n'est plus jointe à vos exports."
                if days < 0
                else f"expire le {when}, dans {days} jour{'s' if days > 1 else ''}."
            )
            + f"\n\nDéposez la nouvelle version dans votre coffre-fort : {base}/coffre-fort\n"
        )
        if doc.org_id in orgs and notify(
            db,
            mailer,
            doc.org_id,
            "vault_expiry",
            f"{doc.id}:{doc.valid_until}:{threshold}",
            subject,
            body,
        ):
            sent += 1
    db.commit()
    return sent


def run_daily(
    db: Session,
    mailer: Mailer,
    now: datetime | None = None,
    storage: ObjectStorage | None = None,
) -> AlertReport:
    """Hourly entry point (unscoped session). Also erases the organizations whose deletion
    date has come (ADR-026) and the security data past its retention (ADR-029)."""
    now = now or datetime.now(UTC)
    today = _paris(now).date()
    report = AlertReport()
    if storage is not None:
        report.organizations_erased = purge_due(db, storage, mailer, now)
    report.retention = purge_expired(db, now)
    report.statuses_refreshed = refresh_stored_statuses(db, today)
    db.commit()
    report.expiry_alerts = send_expiry_alerts(db, mailer, today)
    report.digests = send_digests(db, mailer, now)
    logger.info("daily alerts: %s", report)
    return report
