"""Chiffrage (ADR-049): the lines to price, checked, priced, and written back.

The AI proposes the lines of the buyer's file (which cell takes the price, the hours, the
rate); the server keeps only the proposals the file confirms and reads the quantities itself.
Prices come from the company only: hours × its hourly rate, a price it typed, or its rate
with its own surcharge for an hourly price. Nothing missing is ever guessed. An option (PSE,
variante, « OPTION : … ») is priced like any line but kept out of the offer's total: the buyer
counts it apart, often « pour mémoire ».
"""

import re
import unicodedata
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.price_grid import Cell, Sheet

MAX_LINES = 500
Surcharge = Literal["none", "night", "sunday", "holiday"]
_CELL = re.compile(r"^\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})$")
_SAME_ROW_REF = re.compile(r"^=\s*\+?\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})\s*$")
# the words that open an option's label or rubric (accents folded): « OPTION : … », « PSE n°1 »
_OPTION = re.compile(
    r"^\W*(options?\b|pse\b|variantes?\b|prestations? supplementaires? eventuelles?)"
)


class LineIn(BaseModel):
    """One line as the model proposes it (schema of the prompt ``lecture_bordereau_prix``)."""

    sheet: str = Field(max_length=200)
    section: str = Field(default="", max_length=300)
    label: str = Field(default="", max_length=500)  # a fallback: the label's cell comes first
    label_cell: str | None = Field(default=None, max_length=12)
    unit: str = Field(default="", max_length=50)
    quantity_cell: str | None = Field(default=None, max_length=12)
    price_cell: str = Field(max_length=12)
    hours_cell: str | None = Field(default=None, max_length=12)
    rate_cell: str | None = Field(default=None, max_length=12)
    hourly: bool = False
    surcharge: Surcharge = "none"
    option: bool = False


class PriceReadOut(BaseModel):
    lines: list[LineIn] = Field(default_factory=list, max_length=MAX_LINES)
    notes: list[str] = Field(default_factory=list, max_length=20)


class DocLineIn(BaseModel):
    """One line of a price file that is a document (PDF, Word: a contractor's « fiche
    d'intervention », 25/11), as the model reads it on a page (``lecture_prix_document``)."""

    section: str = Field(default="", max_length=300)
    label: str = Field(max_length=500)
    unit: str = Field(default="", max_length=50)
    quantity: str | None = Field(default=None, max_length=30)  # as written: « 89,83 »
    page: int = Field(ge=1, le=10_000)
    option: bool = False


class DocPriceReadOut(BaseModel):
    lines: list[DocLineIn] = Field(default_factory=list, max_length=MAX_LINES)
    notes: list[str] = Field(default_factory=list, max_length=20)


@dataclass(frozen=True)
class PriceLine:
    id: str  # « Feuille!B5 »: stable across readings of the same file
    sheet: str
    section: str
    label: str
    unit: str
    quantity: Decimal | None
    price_cell: str
    hours_cell: str | None
    rate_cell: str | None
    hourly: bool
    surcharge: Surcharge
    option: bool = False  # priced, out of the total

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sheet": self.sheet,
            "section": self.section,
            "label": self.label,
            "unit": self.unit,
            "quantity": None if self.quantity is None else str(self.quantity),
            "price_cell": self.price_cell,
            "hours_cell": self.hours_cell,
            "rate_cell": self.rate_cell,
            "hourly": self.hourly,
            "surcharge": self.surcharge,
            "option": self.option,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PriceLine":
        qty = d.get("quantity")
        return cls(
            id=d["id"],
            sheet=d["sheet"],
            section=d.get("section") or "",
            label=d["label"],
            unit=d.get("unit") or "",
            quantity=None if qty is None else Decimal(qty),
            price_cell=d["price_cell"],
            hours_cell=d.get("hours_cell"),
            rate_cell=d.get("rate_cell"),
            hourly=bool(d.get("hourly")),
            surcharge=d.get("surcharge") or "none",
            option=bool(d.get("option")),
        )


def _ref(text: str | None) -> str | None:
    """« $B$5 » → « B5 »; None when it is not a cell reference."""
    if not text:
        return None
    match = _CELL.match(text.strip().upper())
    return f"{match.group(1)}{match.group(2)}" if match else None


def _number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.replace(" ", "").replace(" ", "").replace(",", "."))
        except InvalidOperation:
            return None
    return None


def is_option(section: str, label: str) -> bool:
    """« OPTION : Shampouinage moquette », a « PSE n°1 » or « Variante » rubric."""
    return any(_OPTION.match(_fold(text)) for text in (label, section))


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _writable(cell: Cell | None) -> bool:
    """A cell Pilao may write: empty, a number, or a blank text — never a formula or a label."""
    if cell is None:
        return True
    if cell.formula:
        return False
    if isinstance(cell.raw, str):
        return cell.raw.strip() in ("", "-", "€", "- €")
    return isinstance(cell.raw, int | float) and not isinstance(cell.raw, bool)


def validate_lines(
    proposed: list[LineIn], sheets: list[Sheet]
) -> tuple[list[PriceLine], list[str]]:
    by_name = {s.name: s for s in sheets if not s.hidden}
    seen: set[str] = set()
    lines: list[PriceLine] = []
    dropped = 0
    for p in proposed[:MAX_LINES]:
        sheet = by_name.get(p.sheet)
        price = _ref(p.price_cell)
        label_ref = _ref(p.label_cell)
        written = sheet.cells.get(label_ref) if sheet is not None and label_ref else None
        shown = (written.cached if written.formula else written.raw) if written else None
        text = shown if isinstance(shown, str) and shown.strip() else p.label
        label = re.sub(r"\s+", " ", text).strip()[:500]
        if sheet is None or price is None or not label:
            dropped += 1
            continue
        line_id = f"{sheet.name}!{price}"
        if line_id in seen or not _writable(sheet.cells.get(price)):
            dropped += 1
            continue
        seen.add(line_id)

        def helper(text: str | None, taken: set[str], sheet: Sheet = sheet) -> str | None:
            ref = _ref(text)
            if ref is None or ref in taken or not _writable(sheet.cells.get(ref)):
                return None
            return ref

        hours = helper(p.hours_cell, {price})
        rate = helper(p.rate_cell, {price} | ({hours} if hours else set()))
        qty_ref = _ref(p.quantity_cell)
        qty_cell = sheet.cells.get(qty_ref) if qty_ref else None
        quantity = None
        if qty_cell is not None:
            quantity = _number(qty_cell.cached if qty_cell.formula else qty_cell.raw)
        section = re.sub(r"\s+", " ", p.section).strip()
        lines.append(
            PriceLine(
                id=line_id,
                sheet=sheet.name,
                section=section,
                label=label,
                unit=p.unit.strip(),
                quantity=quantity,
                price_cell=price,
                hours_cell=hours,
                rate_cell=rate,
                hourly=p.hourly,
                surcharge=p.surcharge if p.hourly else "none",
                option=p.option or is_option(section, label),
            )
        )
    lines = _fold_copies(lines, by_name)
    warnings = []
    if dropped:
        warnings.append(
            f"{dropped} ligne{'s' if dropped > 1 else ''} proposée{'s' if dropped > 1 else ''} "
            "par la lecture ne correspondai"
            f"{'ent' if dropped > 1 else 't'} à aucune case à remplir : écartée"
            f"{'s' if dropped > 1 else ''}."
        )
    return lines, warnings


_WORD = re.compile(r"[a-z0-9]{3,}")


def _found(label: str, page: str) -> bool:
    """Most of the label's words are on the page (OCR may misread one of them)."""
    words = set(_WORD.findall(_fold(label)))
    if not words:
        return False
    on_page = set(_WORD.findall(_fold(page)))
    return len(words & on_page) >= max(1, round(0.7 * len(words)))


def _compact(text: str) -> str:
    return re.sub(r"[\s\u00a0\u202f]", "", text)


def validate_document_lines(
    proposed: list[DocLineIn], pages: dict[int, str]
) -> tuple[list[PriceLine], list[str]]:
    """The lines of a document, kept only where the cited page has them: the label's words,
    and the quantity as written (else the line stays, its quantity to type). Nothing to
    fill in the document itself: the company's prices go to a DPGF Pilao writes."""
    lines: list[PriceLine] = []
    warnings: list[str] = []
    seen: set[tuple[str, str, int]] = set()
    lost = 0
    for item in proposed:
        text = pages.get(item.page)
        label = re.sub(r"\s+", " ", item.label).strip()
        if text is None or not label or not _found(label, text):
            lost += 1
            continue
        key = (_fold(item.section).strip(), _fold(label), item.page)
        if key in seen:
            continue
        seen.add(key)
        quantity = _number(item.quantity) if item.quantity else None
        if quantity is not None and _compact(item.quantity or "") not in _compact(text):
            warnings.append(
                f"« {label[:80]} » : la quantité {item.quantity} n'est pas écrite page "
                f"{item.page}, saisissez-la."
            )
            quantity = None
        section = re.sub(r"\s+", " ", item.section).strip()
        unit = item.unit.strip()
        lines.append(
            PriceLine(
                id=f"p{item.page}-{len(lines) + 1:03d}",
                sheet="",
                section=section,
                label=label,
                unit=unit,
                quantity=quantity,
                price_cell="",
                hours_cell=None,
                rate_cell=None,
                hourly=normalize_unit(unit) == "heure",
                surcharge="none",
                option=item.option or is_option(section, label),
            )
        )
        if len(lines) >= MAX_LINES:
            break
    if lost:
        warnings.append(
            f"{lost} ligne{'s' if lost > 1 else ''} proposée{'s' if lost > 1 else ''} par "
            f"la lecture n'{'ont' if lost > 1 else 'a'} pas été retrouvée"
            f"{'s' if lost > 1 else ''} dans le document : vérifiez qu'aucune ne manque."
        )
    return lines, warnings


def _split(ref: str) -> tuple[str, int]:
    match = _CELL.match(ref)
    assert match is not None
    return match.group(1), int(match.group(2))


def _copy_columns(sheet: Sheet) -> dict[str, set[str]]:
    """Column → the columns that repeat it row by row (« H5: =B5 » makes H a copy of B)."""
    copies: dict[str, set[str]] = {}
    for ref, cell in sheet.cells.items():
        match = _SAME_ROW_REF.match(cell.raw) if cell.formula else None
        if match and int(match.group(2)) == _split(ref)[1] and match.group(1) != _split(ref)[0]:
            copies.setdefault(match.group(1), set()).add(_split(ref)[0])
    return copies


def _fold_copies(lines: list[PriceLine], sheets: dict[str, Sheet]) -> list[PriceLine]:
    """A line given in a column that only repeats a price column (a DQE beside its BPU) is
    the same line: folded into the line of the price column (which takes its quantity if it
    had none), or moved there when the model gave only the copy. The copy cell is then found
    as a broken link and receives the price too."""
    price_cols = {(ln.sheet, _split(ln.price_cell)[0]) for ln in lines}
    by_cell = {(ln.sheet, ln.price_cell): i for i, ln in enumerate(lines)}
    kept: list[PriceLine | None] = list(lines)
    copy_columns = {name: _copy_columns(sheets[name]) for name in {ln.sheet for ln in lines}}
    for i, ln in enumerate(lines):
        col, row = _split(ln.price_cell)
        sheet = sheets[ln.sheet]
        origins = [
            c
            for c, copies in copy_columns[ln.sheet].items()
            if col in copies and (ln.sheet, c) in price_cols
        ]
        if len(origins) != 1:
            continue
        origin = f"{origins[0]}{row}"
        if (ln.sheet, origin) in by_cell:
            j = by_cell[(ln.sheet, origin)]
            target = kept[j]
            if target is not None and target.quantity is None and ln.quantity is not None:
                kept[j] = replace(target, quantity=ln.quantity)
            kept[i] = None
        elif _writable(sheet.cells.get(origin)):
            kept[i] = replace(ln, id=f"{ln.sheet}!{origin}", price_cell=origin)
            by_cell[(ln.sheet, origin)] = i
    return [ln for ln in kept if ln is not None]


def broken_links(lines: list[PriceLine], sheets: list[Sheet]) -> dict[str, list[str]]:
    """Cells that should repeat a line's price but hold a fixed number instead.

    A column « mirrors » a price column when, on the rows of other lines, it holds « =B5 »
    (the price of its own row). On a line's row where that column holds a plain number
    instead (Rillieux, yearly service: 0), the link is broken: the price goes there too.
    """
    by_name = {s.name: s for s in sheets}
    taken = {
        (ln.sheet, c) for ln in lines for c in (ln.price_cell, ln.hours_cell, ln.rate_cell) if c
    }
    mirror_cols: dict[tuple[str, str], set[str]] = {}
    for ln in lines:
        col, row = _split(ln.price_cell)
        for ref, cell in by_name[ln.sheet].cells.items():
            match = _SAME_ROW_REF.match(cell.raw) if cell.formula else None
            if match and match.group(1) == col and int(match.group(2)) == row:
                mirror_cols.setdefault((ln.sheet, col), set()).add(_split(ref)[0])
    found: dict[str, list[str]] = {}
    for ln in lines:
        col, row = _split(ln.price_cell)
        for other in sorted(mirror_cols.get((ln.sheet, col), set())):
            ref = f"{other}{row}"
            fixed = by_name[ln.sheet].cells.get(ref)
            if (
                fixed is not None
                and not fixed.formula
                and (ln.sheet, ref) not in taken
                and isinstance(fixed.raw, int | float)
                and not isinstance(fixed.raw, bool)
            ):
                found.setdefault(ln.id, []).append(ref)
    return found


@dataclass(frozen=True)
class Rates:
    hourly_rate_cents: int | None
    night_pct: int | None
    sunday_pct: int | None
    holiday_pct: int | None

    def surcharge_pct(self, surcharge: Surcharge) -> int | None:
        if surcharge == "none":
            return 0
        return {"night": self.night_pct, "sunday": self.sunday_pct, "holiday": self.holiday_pct}[
            surcharge
        ]


@dataclass(frozen=True)
class LinePrice:
    id: str
    hours: Decimal | None
    rate_cents: int | None  # the rate used (hours × rate)
    price_cents: int | None
    total_cents: int | None
    source: Literal["hours", "price", "hourly", "none", "excluded"]

    @property
    def missing(self) -> bool:
        return self.price_cents is None and self.source != "excluded"


@dataclass(frozen=True)
class Priced:
    lines: list[LinePrice]
    total_cents: int  # the offer: options left out
    missing_count: int
    options_cents: int = 0  # the options' own total


def _cents(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def parse_hours(value: Any) -> Decimal | None:
    hours = _number(value)
    if hours is None or hours <= 0 or hours > 10_000:
        return None
    return hours.normalize()


def compute(
    lines: list[PriceLine],
    entries: dict[str, dict[str, Any]],
    rates: Rates,
    rate_cents: int | None,
    excluded: set[str] | frozenset[str] = frozenset(),
) -> Priced:
    """``rate_cents``: this dossier's hourly rate, else the company's. ``excluded``: the
    rubriques the company does not price (ADR-052): their lines are left as the buyer gave
    them, neither priced, nor counted, nor missing."""
    rate = rate_cents if rate_cents is not None else rates.hourly_rate_cents
    out: list[LinePrice] = []
    total = options = 0
    for ln in lines:
        if ln.section in excluded:
            out.append(LinePrice(ln.id, None, None, None, None, "excluded"))
            continue
        entry = entries.get(ln.id) or {}
        typed = entry.get("price_cents")
        hours = parse_hours(entry.get("hours"))
        price: int | None = None
        source: Literal["hours", "price", "hourly", "none", "excluded"] = "none"
        used_rate: int | None = None
        if isinstance(typed, int) and not isinstance(typed, bool) and typed >= 0:
            price, source = typed, "price"
        elif ln.hourly:
            pct = rates.surcharge_pct(ln.surcharge)
            if rate is not None and pct is not None:
                price = _cents(Decimal(rate) * (100 + pct) / 100)
                source, used_rate = "hourly", rate
        elif hours is not None and rate is not None:
            price, source, used_rate = _cents(hours * rate), "hours", rate
        line_total = None
        if price is not None and ln.quantity is not None:
            line_total = _cents(ln.quantity * price)
            if ln.option:
                options += line_total
            else:
                total += line_total
        out.append(LinePrice(ln.id, hours, used_rate, price, line_total, source))
    return Priced(out, total, sum(1 for p in out if p.missing), options)


def fill_writes(
    lines: list[PriceLine], priced: Priced, mirrors: dict[str, list[str]]
) -> dict[str, dict[str, float]]:
    """What goes into the buyer's file: prices (and their broken links), hours and rate."""
    by_id = {p.id: p for p in priced.lines}
    writes: dict[str, dict[str, float]] = {}
    for ln in lines:
        p = by_id[ln.id]
        if p.price_cents is None:
            continue  # left as the buyer gave it
        cells = writes.setdefault(ln.sheet, {})
        euros = p.price_cents / 100
        cells[ln.price_cell] = euros
        for ref in mirrors.get(ln.id, []):
            cells[ref] = euros
        if p.source == "hours" and p.hours is not None and p.rate_cents is not None:
            if ln.hours_cell:
                cells[ln.hours_cell] = float(p.hours)
            if ln.rate_cell:
                cells[ln.rate_cell] = p.rate_cents / 100
    return {sheet: cells for sheet, cells in writes.items() if cells}


def _text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def hours_summary(lines: list[PriceLine], priced: Priced) -> dict[str, Any] | None:
    """The hours the company typed, for the memoir (never a price)."""
    by_id = {p.id: p for p in priced.lines}
    rows: list[dict[str, Any]] = []
    total = Decimal(0)
    for ln in lines:
        p = by_id[ln.id]
        if p.hours is None or ln.hourly or ln.option:
            continue
        row: dict[str, Any] = {
            "rubrique": ln.section,
            "libelle": ln.label,
            "heures_par_unite": _text(p.hours),
            "unite": ln.unit,
            "quantite": None if ln.quantity is None else _text(ln.quantity),
            "heures_annuelles": None,
        }
        if ln.quantity is not None:
            yearly = p.hours * ln.quantity
            row["heures_annuelles"] = _text(yearly)
            total += yearly
        rows.append(row)
    if not rows:
        return None
    return {"lignes": rows, "heures_totales": _text(total)}


# ---------- « Ma liste de prix » (ADR-052) ---------------------------------------------------

_UNITS = [
    (r"m\s*(2|²)", "m²"),
    (r"m\s*(3|³)", "m³"),
    (r"ml|m\.?l\.?|m[eè]tres?\s+lin[ée]aires?", "ml"),
    (r"h|hr?s?|heures?", "heure"),
    (r"j|jours?", "jour"),
    (r"ff|forfaits?|ens(emble)?|fft", "forfait"),
    (r"u|un|unit[ée]s?|pce|pi[eè]ces?|nb|nombre", "u"),
    (r"passages?", "passage"),
    (r"mois", "mois"),
]


def normalize_unit(unit: str) -> str:
    """« M2 », « m 2 », « m² » → « m² » ; « h », « Heures » → « heure » ; « ens », « ff » →
    « forfait »… so a line and a service can be compared whatever the spelling."""
    value = re.sub(r"\s+", " ", (unit or "").strip().lower())
    for pattern, name in _UNITS:
        if re.fullmatch(pattern, value):
            return name
    return value


@dataclass(frozen=True)
class ServiceRef:
    """A service of the company's price list, as matching needs it."""

    id: str
    name: str
    unit: str
    price_cents: int


class MatchIn(BaseModel):
    """One line the model recognised as a service of the list (prompt
    ``rapprochement_prestations``)."""

    line: str = Field(max_length=80)
    service: str = Field(max_length=80)


class MatchOut(BaseModel):
    matches: list[MatchIn] = Field(default_factory=list, max_length=MAX_LINES)


def validate_matches(
    proposed: list[MatchIn], lines: list[PriceLine], services: list[ServiceRef]
) -> dict[str, str]:
    """Line id → service id, kept only for known lines and services of the same unit: a
    price per m² never fills an hourly line."""
    by_line = {ln.id: ln for ln in lines}
    by_service = {s.id: s for s in services}
    out: dict[str, str] = {}
    for m in proposed:
        line, service = by_line.get(m.line), by_service.get(m.service)
        if line is None or service is None or m.line in out:
            continue
        if normalize_unit(line.unit) != normalize_unit(service.unit):
            continue
        out[m.line] = m.service
    return out


def default_excluded(lines: list[PriceLine], matched: dict[str, str]) -> list[str]:
    """The rubriques set aside in a consultation: those where no line matched a service.
    Nothing is set aside when nothing matched at all (the company decides by hand)."""
    if not matched:
        return []
    kept = {ln.section for ln in lines if ln.id in matched}
    out: list[str] = []
    for ln in lines:
        if ln.section not in kept and ln.section not in out:
            out.append(ln.section)
    return out
