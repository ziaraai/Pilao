"""Compliance vault rules (US-5.1 / US-5.2): kinds, validity, status, help links.

Statuses are *derived* from the dates and the SIREN check, so a document never shows "valid"
after its expiry date, whatever the stored value says.
"""

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

KINDS = (
    "kbis",
    "rne_certificate",
    "urssaf_vigilance",
    "tax_compliance",
    "cibtp_certificate",
    "insurance_rc_pro",
    "insurance_decennale",
    "qualification",
    "other",
)
STATUSES = ("pending_review", "valid", "expiring", "expired", "mismatch")
EXPIRING_DAYS = 30
ALERT_DAYS = (30, 7)  # e-mail alerts (P3-05)
# Kinds for which an expiry date is mandatory to confirm (everything but "other").
DATE_REQUIRED = frozenset(KINDS) - {"other"}
VALIDITY_RULES = ("written", "urssaf_6_months", "kbis_3_months")

# Commonly requested documents; "either of" groups satisfy one need.
RECOMMENDED: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Justificatif d'immatriculation (Kbis ou attestation RNE)", ("kbis", "rne_certificate")),
    ("Attestation de vigilance URSSAF", ("urssaf_vigilance",)),
    ("Attestation de régularité fiscale", ("tax_compliance",)),
    ("Assurance responsabilité civile professionnelle", ("insurance_rc_pro",)),
)

# Entry points only: deep links were not verified from the development environment.
HELP_LINKS: dict[str, dict[str, str]] = {
    "kbis": {"label": "Extrait Kbis (Infogreffe)", "url": "https://www.infogreffe.fr"},
    "rne_certificate": {
        "label": "Attestation d'immatriculation RNE (INPI)",
        "url": "https://data.inpi.fr/",
    },
    "urssaf_vigilance": {
        "label": "Attestation de vigilance (espace en ligne URSSAF)",
        "url": "https://www.urssaf.fr",
    },
    "tax_compliance": {
        "label": "Attestation de régularité fiscale (impots.gouv.fr, espace professionnel)",
        "url": "https://www.impots.gouv.fr",
    },
    "cibtp_certificate": {
        "label": "Certificat CIBTP (caisse de congés payés)",
        "url": "https://www.cibtp.fr",
    },
}


def paris_today() -> date:
    return datetime.now(ZoneInfo("Europe/Paris")).date()


def add_months(d: date, months: int) -> date:
    index = d.month - 1 + months
    year, month = d.year + index // 12, index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def derive_valid_until(
    kind: str, issued_at: date | None, written: date | None
) -> tuple[date | None, str | None]:
    """Suggested expiry date and the rule it comes from (the user can always correct it)."""
    if written is not None:
        return written, "written"
    if issued_at is None:
        return None, None
    if kind == "urssaf_vigilance":
        return add_months(issued_at, 6), "urssaf_6_months"
    if kind == "kbis":
        return add_months(issued_at, 3), "kbis_3_months"
    return None, None


def siren_matches(siren_on_document: str | None, org_siren: str) -> bool:
    return siren_on_document is None or siren_on_document == org_siren


@dataclass(frozen=True)
class StatusInfo:
    status: str
    days_left: int | None


def effective_status(
    *, confirmed: bool, siren_ok: bool, valid_until: date | None, today: date
) -> StatusInfo:
    if not confirmed:
        return StatusInfo("pending_review", None)
    days_left = (valid_until - today).days if valid_until else None
    if not siren_ok:
        return StatusInfo("mismatch", days_left)
    if days_left is None:
        return StatusInfo("valid", None)
    if days_left < 0:
        return StatusInfo("expired", days_left)
    if days_left <= EXPIRING_DAYS:
        return StatusInfo("expiring", days_left)
    return StatusInfo("valid", days_left)


def is_usable(status: str) -> bool:
    """Only confirmed, in-date documents may be exported or counted as available."""
    return status in ("valid", "expiring")
