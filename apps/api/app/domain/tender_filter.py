"""Deterministic pre-filter of the watch (US-2.2 CA1), before any AI call.

A notice passes for a company when: (a CPV code OR a keyword matches) AND the place
matches AND the deadline is in the future AND the amount is in the company's range (when
both are known). An excluded keyword rejects it. Each decision says why, in French.

CPV codes are hierarchical: trailing zeros mark the level (90910000 = cleaning services,
90911200 = building cleaning). A company code matches every code below it.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

_WORD = re.compile(r"[a-z0-9]+")


def plain(text: str) -> str:
    """Lower case, without accents: « Propreté » and « proprete » compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _cpv_prefix(code: str) -> str:
    digits = code.split("-")[0].strip()[:8]
    return digits.rstrip("0") or digits[:2]


def cpv_hits(company_codes: list[str], tender_codes: list[str]) -> list[str]:
    """Company codes that cover at least one of the notice's codes."""
    tender = [c.split("-")[0].strip() for c in tender_codes]
    return [code for code in company_codes if any(t.startswith(_cpv_prefix(code)) for t in tender)]


def covered_codes(company_codes: list[str], tender_codes: list[str]) -> list[str]:
    """The notice's codes covered by the company's (what the user recognizes on the notice)."""
    prefixes = [_cpv_prefix(c) for c in company_codes]
    return list(
        dict.fromkeys(
            t
            for t in (c.split("-")[0].strip() for c in tender_codes)
            if any(t.startswith(p) for p in prefixes)
        )
    )


def keyword_hits(keywords: list[str], text: str) -> list[str]:
    """Keywords found as whole words (a multi-word keyword as a phrase), accents and plural
    ignored."""
    words = " ".join(_WORD.findall(plain(text)))
    found = []
    for keyword in keywords:
        needle = " ".join(_WORD.findall(plain(keyword)))
        # the plural counts too: « nettoyage » finds « nettoyages », « bureau » « bureaux »
        if needle and re.search(rf"(?<![a-z0-9]){re.escape(needle)}[sx]?(?![a-z0-9])", words):
            found.append(keyword)
    return found


@dataclass(frozen=True)
class CompanyFilter:
    cpv_codes: list[str] = field(default_factory=list)
    keywords_include: list[str] = field(default_factory=list)
    keywords_exclude: list[str] = field(default_factory=list)
    departments: list[str] = field(default_factory=list)  # empty = all of France
    min_amount_cents: int | None = None
    max_amount_cents: int | None = None

    @property
    def watches_something(self) -> bool:
        return bool(self.cpv_codes or self.keywords_include)


@dataclass(frozen=True)
class TenderFacts:
    title: str
    description: str | None
    lot_titles: list[str]
    cpv_codes: list[str]
    departments: list[str]
    estimated_amount_cents: int | None
    deadline_at: datetime | None


@dataclass(frozen=True)
class Decision:
    passed: bool
    reasons: list[str]  # why it matches (shown to the user)
    rejected: str | None = None  # why not (for tests and logs)


def prefilter(company: CompanyFilter, tender: TenderFacts, now: datetime) -> Decision:
    if not company.watches_something:
        return Decision(False, [], "aucun code CPV ni mot-clé dans le profil")
    text = " ".join([tender.title, tender.description or "", *tender.lot_titles])
    excluded = keyword_hits(company.keywords_exclude, text)
    if excluded:
        return Decision(False, [], f"mot-clé exclu : {excluded[0]}")
    cpv = covered_codes(company.cpv_codes, tender.cpv_codes)
    words = keyword_hits(company.keywords_include, text)
    if not cpv and not words:
        return Decision(False, [], "ni code CPV ni mot-clé")
    reasons = [f"code CPV {c}" for c in cpv] + [f"mot-clé « {w} »" for w in words]

    if company.departments:
        if not tender.departments:
            reasons.append("lieu non précisé dans l'annonce")
        else:
            common = [d for d in tender.departments if d in company.departments]
            if not common:
                return Decision(False, [], "hors de vos départements")
            reasons.append(f"département {', '.join(common)}")

    if tender.deadline_at is not None and tender.deadline_at <= now:
        return Decision(False, [], "date limite dépassée")

    amount = tender.estimated_amount_cents
    if amount is not None:
        if company.min_amount_cents is not None and amount < company.min_amount_cents:
            return Decision(False, [], "montant sous votre minimum")
        if company.max_amount_cents is not None and amount > company.max_amount_cents:
            return Decision(False, [], "montant au-dessus de votre maximum")
    return Decision(True, reasons)


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(plain(text)) if len(w) > 3}


def similar_titles(a: str, b: str) -> bool:
    """Same contract published twice (BOAMP and TED): most significant words in common."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.5


def same_buyer(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta) and (ta <= tb or tb <= ta)
