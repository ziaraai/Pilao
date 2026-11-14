"""Indicative Go / No-Go opinion (US-3.3), from deterministic rules — no AI involved.

Each factor says what was checked and why; a factor that cannot be checked is reported as
"unknown" instead of being guessed. The verdict is only an aid: the company decides.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.domain.dce import normalize as _norm
from app.domain.framework_amounts import FrameworkAmounts, describe
from app.domain.vault import KINDS as VAULT_KINDS

DISCLAIMER = (
    "Avis indicatif calculé à partir du DCE et de votre profil : la décision vous appartient."
)

# Loose names of documents in a RC -> compliance vault kind.
_DOC_PATTERNS: tuple[tuple[str, str], ...] = (
    ("urssaf_vigilance", r"urssaf|vigilance"),
    ("kbis", r"kbis|extrait k\b|registre du commerce"),
    ("rne_certificate", r"\brne\b|registre national des entreprises"),
    ("tax_compliance", r"fiscal|impots|dgfip|regularite fiscale"),
    ("insurance_decennale", r"decennale"),
    ("insurance_rc_pro", r"responsabilite civile|rc pro|assurance"),
    ("cibtp_certificate", r"cibtp|conges payes"),
    ("qualification", r"qualibat|qualipropre|qualification|certification iso|\biso\b"),
)


def compliance_kind_for(name: str, declared: str | None) -> str | None:
    """Vault kind matching a required document, from the model's hint or the document name."""
    if declared in VAULT_KINDS and declared != "other":
        return declared
    normalized = _norm(name)
    for kind, pattern in _DOC_PATTERNS:
        if re.search(pattern, normalized):
            return kind
    return None


@dataclass(frozen=True)
class VaultEntry:
    kind: str
    status: str  # effective status from domain.vault
    valid_until: date | None


@dataclass(frozen=True)
class DocumentCheck:
    name: str
    phase: str
    compliance_kind: str | None
    status: str  # available | expires_before_deadline | expired | unconfirmed | mismatch | missing | to_prepare
    detail: str


_STATUS_RANK = {"valid": 0, "expiring": 1, "pending_review": 2, "mismatch": 3, "expired": 4}


def check_documents(
    required: list[tuple[str, str, str | None]],
    vault: list[VaultEntry],
    deadline: datetime | None,
) -> list[DocumentCheck]:
    """``required`` = [(name, phase, declared kind)]. Kbis and RNE certificate are
    interchangeable here (open question Q2: some buyers may still insist on a Kbis)."""
    checks = []
    for name, phase, declared in required:
        kind = compliance_kind_for(name, declared)
        if kind is None:
            checks.append(
                DocumentCheck(name, phase, None, "to_prepare", "Pièce à préparer pour ce dossier.")
            )
            continue
        accepted = {kind} | (
            {"kbis", "rne_certificate"} if kind in ("kbis", "rne_certificate") else set()
        )
        # Among usable documents, the one valid the longest (a renewed attestation next to
        # the old one); no end date means no expiry.
        candidates = sorted(
            (v for v in vault if v.kind in accepted),
            key=lambda v: (
                0 if v.status in ("valid", "expiring") else _STATUS_RANK.get(v.status, 9),
                -(v.valid_until or date.max).toordinal(),
            ),
        )
        best = candidates[0] if candidates else None
        if best is None:
            checks.append(DocumentCheck(name, phase, kind, "missing", "Absent du coffre-fort."))
        elif best.status in ("valid", "expiring"):
            if deadline and best.valid_until and best.valid_until < deadline.date():
                checks.append(
                    DocumentCheck(
                        name,
                        phase,
                        kind,
                        "expires_before_deadline",
                        f"Expire le {best.valid_until:%d/%m/%Y}, avant la date limite de remise.",
                    )
                )
            else:
                note = (
                    " (attestation RNE : vérifiez que l'acheteur l'accepte)"
                    if best.kind != kind
                    else ""
                )
                checks.append(
                    DocumentCheck(
                        name,
                        phase,
                        kind,
                        "available",
                        "Disponible dans le coffre-fort" + note + ".",
                    )
                )
        elif best.status == "pending_review":
            checks.append(
                DocumentCheck(name, phase, kind, "unconfirmed", "Déposé mais pas encore confirmé.")
            )
        elif best.status == "mismatch":
            checks.append(
                DocumentCheck(
                    name, phase, kind, "mismatch", "Le SIREN du document ne correspond pas."
                )
            )
        else:
            checks.append(DocumentCheck(name, phase, kind, "expired", "Expiré : à renouveler."))
    return checks


@dataclass(frozen=True)
class Factor:
    label: str
    status: str  # ok | warning | blocking | unknown
    detail: str


@dataclass
class Opinion:
    score: int
    verdict: str  # go | to_study | no_go
    factors: list[Factor] = field(default_factory=list)
    disclaimer: str = DISCLAIMER


@dataclass(frozen=True)
class Inputs:
    now: datetime
    deadline: datetime | None
    estimated_amount_cents: int | None
    min_amount_cents: int | None
    max_amount_cents: int | None
    profile_keywords: list[str]  # included keywords + trade keywords
    excluded_keywords: list[str]
    tender_text: str  # title + requirements, used for the trade fit
    documents: list[DocumentCheck]
    blocking_watch_points: list[str]
    visit_mandatory: bool | None
    visit_dates: list[datetime]
    framework: FrameworkAmounts | None = None  # accord-cadre minimum / maximum


def _framework_factor(i: Inputs, fa: FrameworkAmounts, factors: list[Factor]) -> int:
    """No estimate but an accord-cadre range: judged on the overlap with the company's range
    (the guaranteed minimum above its maximum, or the whole range under its minimum)."""
    what = f"Accord-cadre {describe(fa)}"
    low, high = fa.minimum_cents, fa.maximum_cents
    if i.min_amount_cents is not None and high is not None and high < i.min_amount_cents:
        factors.append(Factor("Montant", "warning", f"{what} : sous votre minimum."))
        return -15
    if i.max_amount_cents is not None and low is not None and low > i.max_amount_cents:
        factors.append(Factor("Montant", "warning", f"{what} : au-dessus de votre maximum."))
        return -20
    factors.append(Factor("Montant", "ok", f"{what} : dans votre fourchette."))
    return 0


def opinion(i: Inputs) -> Opinion:
    score, factors = 100, []
    text = _norm(i.tender_text)

    excluded = [k for k in i.excluded_keywords if _norm(k) and _norm(k) in text]
    # The same word can come from the profile and from a trade: list it once.
    matched = list(
        dict.fromkeys(_norm(k) for k in i.profile_keywords if _norm(k) and _norm(k) in text)
    )
    if excluded:
        score -= 40
        factors.append(
            Factor("Métier", "blocking", f"Contient un mot-clé exclu : {', '.join(excluded[:3])}.")
        )
    elif not i.profile_keywords:
        factors.append(
            Factor("Métier", "unknown", "Profil sans mots-clés : adéquation non évaluée.")
        )
    elif matched:
        factors.append(
            Factor("Métier", "ok", f"Correspond à votre activité ({', '.join(matched[:3])}).")
        )
    else:
        score -= 30
        factors.append(
            Factor(
                "Métier",
                "warning",
                "Aucun de vos mots-clés n'apparaît dans l'objet ou les exigences.",
            )
        )

    amount = i.estimated_amount_cents
    if amount is None and i.framework is not None:
        score += _framework_factor(i, i.framework, factors)
    elif amount is None:
        factors.append(Factor("Montant", "unknown", "Montant estimé non indiqué dans le DCE."))
    elif i.min_amount_cents is not None and amount < i.min_amount_cents:
        score -= 15
        factors.append(
            Factor(
                "Montant",
                "warning",
                f"{amount / 100:,.0f} € HT : sous votre minimum.".replace(",", " "),
            )
        )
    elif i.max_amount_cents is not None and amount > i.max_amount_cents:
        score -= 20
        factors.append(
            Factor(
                "Montant",
                "warning",
                f"{amount / 100:,.0f} € HT : au-dessus de votre maximum.".replace(",", " "),
            )
        )
    else:
        factors.append(
            Factor(
                "Montant",
                "ok",
                f"{amount / 100:,.0f} € HT : dans votre fourchette.".replace(",", " "),
            )
        )

    if i.deadline is None:
        factors.append(
            Factor(
                "Délai", "unknown", "Date limite de remise non trouvée : vérifiez-la dans le RC."
            )
        )
    else:
        days = (i.deadline - i.now).total_seconds() / 86400
        if days < 0:
            score = 0
            factors.append(Factor("Délai", "blocking", "La date limite de remise est dépassée."))
        elif days < 3:
            score -= 40
            factors.append(
                Factor("Délai", "blocking", f"Moins de 3 jours pour répondre ({days:.0f} j).")
            )
        elif days < 10:
            score -= 15
            factors.append(
                Factor("Délai", "warning", f"{days:.0f} jours pour répondre : délai serré.")
            )
        else:
            factors.append(Factor("Délai", "ok", f"{days:.0f} jours pour répondre."))

    if i.visit_mandatory and i.visit_dates and all(d < i.now for d in i.visit_dates):
        score -= 40
        factors.append(Factor("Visite", "blocking", "La visite obligatoire est déjà passée."))
    elif i.visit_mandatory:
        factors.append(Factor("Visite", "warning", "Visite obligatoire : à planifier."))

    problems = [
        d
        for d in i.documents
        if d.status in ("missing", "expired", "expires_before_deadline", "mismatch")
    ]
    if problems:
        score -= min(30, 10 * len(problems))
        factors.append(
            Factor(
                "Pièces",
                "warning",
                f"{len(problems)} pièce(s) à obtenir ou renouveler : "
                + ", ".join(d.name for d in problems[:4])
                + ".",
            )
        )
    elif i.documents:
        factors.append(Factor("Pièces", "ok", "Pièces administratives disponibles ou à préparer."))

    if i.blocking_watch_points:
        score -= min(30, 15 * len(i.blocking_watch_points))
        factors.append(
            Factor("Points de vigilance", "blocking", "; ".join(i.blocking_watch_points[:2]))
        )

    score = max(0, min(100, score))
    verdict = "go" if score >= 70 else "to_study" if score >= 40 else "no_go"
    if any(f.status == "blocking" for f in factors) and verdict == "go":
        verdict = "to_study"
    return Opinion(score, verdict, factors)
