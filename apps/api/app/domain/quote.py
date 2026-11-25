"""The company's own quote for a consultation (ADR-052): pure rules.

The quote's table comes from the price file as priced in the « Prix » tab (rubriques set aside
left out, options apart). « Prestations comprises » are what the CCTP asks for the rubriques
priced: the AI reads the CCTP pages that name them, and every bullet must cite one of the pages
it was sent (file + page); any other is dropped. Nothing else comes from the AI.
"""

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, Field

from app.domain.pricing import Priced, PriceLine

MAX_INCLUSIONS = 12
# words of a rubrique or a line that name no work (folded, ≥ 5 letters)
_STOP = frozenset(
    {
        "avant",
        "apres",
        "compris",
        "comprise",
        "compte",
        "ensemble",
        "forfait",
        "total",
        "totaux",
        "batiment",
        "niveau",
        "niveaux",
        "selon",
        "suivant",
        "toutes",
        "travaux",
        "prestation",
        "prestations",
        "sous-total",
        "option",
        "options",
        "variante",
        "lot",
    }
)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", _fold(text)))


def signature_line(company: str, name: str | None, role: str | None) -> str:
    """« Pour ENG PRO : M. Exemple, gérant ». A signatory that is only the company's name
    (« ENG-PRO, ENG-PRO », 25/11) names nobody: the line is left to fill in by hand."""
    own = _words(company)

    def person(value: str | None) -> str | None:
        words = _words(value or "")
        return value.strip() if value and words and words not in own else None

    who = person(name)
    if who is None:
        return f"Pour {company} — nom et qualité du signataire :"
    quality = person(role)
    return f"Pour {company} : {who}" + (f", {quality}" if quality else "")


def _stem(word: str) -> str:
    return word[:-1] if word.endswith("s") and len(word) > 5 else word


def terms(texts: Iterable[str]) -> list[str]:
    """The words that name the work priced (« nettoyage », « reception »), folded, in order."""
    out: list[str] = []
    for text in texts:
        for word in re.findall(r"[a-z]+", _fold(text)):
            word = _stem(word)
            if len(word) >= 5 and word not in _STOP and word not in out:
                out.append(word)
    return out


@dataclass(frozen=True)
class Page:
    file: str  # the DCE piece's name, as cited in the quote
    page: int
    text: str


def _score(page: Page, words: list[str]) -> int:
    text = " ".join(_stem(w) for w in re.findall(r"[a-z]+", _fold(page.text)))
    return sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", text))


def pick_pages(
    pages: list[Page], words: list[str], *, max_pages: int = 10, max_chars: int = 30_000
) -> list[Page]:
    """The CCTP pages that name the work priced, best first within the limits, given back in
    the document's order. None when no page names it: then the AI is not called."""
    scored = [(s, p) for p in pages if (s := _score(p, words)) > 0]
    scored.sort(key=lambda sp: (-sp[0], sp[1].file, sp[1].page))
    kept: list[Page] = []
    size = 0
    for _, page in scored:
        if len(kept) == max_pages:
            break
        if size + len(page.text) > max_chars:
            continue
        kept.append(page)
        size += len(page.text)
    return sorted(kept, key=lambda p: (p.file, p.page))


class InclusionIn(BaseModel):
    text: str = Field(max_length=400)
    file: str = Field(max_length=300)
    page: int


class InclusionsOut(BaseModel):
    inclusions: list[InclusionIn] = Field(default_factory=list, max_length=30)


def keep_sourced(proposed: list[InclusionIn], sent: list[Page]) -> list[dict[str, object]]:
    """The bullets citing a page sent, once each, at most ``MAX_INCLUSIONS``."""
    allowed = {(p.file, p.page) for p in sent}
    seen: set[str] = set()
    out: list[dict[str, object]] = []
    for item in proposed:
        text = re.sub(r"\s+", " ", item.text).strip()
        key = _fold(text)
        if not text or key in seen or (item.file, item.page) not in allowed:
            continue
        seen.add(key)
        out.append({"text": text, "file": item.file, "page": item.page})
        if len(out) == MAX_INCLUSIONS:
            break
    return out


def vat_of(ht_cents: int, vat_bp: int) -> int:
    """The VAT on an amount, rounded half up to the cent (``vat_bp``: 2000 = 20 %)."""
    return (ht_cents * vat_bp + 5000) // 10000


@dataclass(frozen=True)
class QuoteRow:
    section: str
    label: str
    unit: str
    quantity: Decimal | None
    price_cents: int | None
    total_cents: int | None


@dataclass(frozen=True)
class QuoteTable:
    rows: list[QuoteRow]
    options: list[QuoteRow]
    total_ht_cents: int
    options_cents: int

    @property
    def has_totals(self) -> bool:
        return any(r.total_cents is not None for r in self.rows)


def quote_table(lines: list[PriceLine], priced: Priced) -> QuoteTable:
    """The priced lines, in the file's order; the rubriques set aside left out."""
    by_id = {p.id: p for p in priced.lines}
    rows: list[QuoteRow] = []
    options: list[QuoteRow] = []
    for ln in lines:
        p = by_id[ln.id]
        if p.source == "excluded":
            continue
        row = QuoteRow(ln.section, ln.label, ln.unit, ln.quantity, p.price_cents, p.total_cents)
        (options if ln.option else rows).append(row)
    return QuoteTable(rows, options, priced.total_cents, priced.options_cents)


def fingerprint(table: QuoteTable) -> str:
    """What the quote was made from: a price, a quantity, a line set aside or taken back, a
    new rate in the profile all change it (the quote then says its prices changed)."""

    def rows(items: list[QuoteRow]) -> list[list[object]]:
        return [
            [r.section, r.label, r.unit, str(r.quantity), r.price_cents, r.total_cents]
            for r in items
        ]

    data = [rows(table.rows), rows(table.options), table.total_ht_cents, table.options_cents]
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode()).hexdigest()
