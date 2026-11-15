"""Chiffrage (ADR-049): the lines to price, checked, priced, and written back.

The AI proposes the lines of the buyer's file (which cell takes the price, the hours, the
rate); the server keeps only the proposals the file confirms and reads the quantities itself.
Prices come from the company only: hours × its hourly rate, a price it typed, or its rate
with its own surcharge for an hourly price. Nothing missing is ever guessed.
"""

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.price_grid import Cell, Sheet

MAX_LINES = 500
Surcharge = Literal["none", "night", "sunday", "holiday"]
_CELL = re.compile(r"^\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})$")
_SAME_ROW_REF = re.compile(r"^=\s*\+?\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})\s*$")


class LineIn(BaseModel):
    """One line as the model proposes it (schema of the prompt ``lecture_bordereau_prix``)."""

    sheet: str = Field(max_length=200)
    section: str = Field(default="", max_length=300)
    label: str = Field(max_length=500)
    unit: str = Field(default="", max_length=50)
    quantity_cell: str | None = Field(default=None, max_length=12)
    price_cell: str = Field(max_length=12)
    hours_cell: str | None = Field(default=None, max_length=12)
    rate_cell: str | None = Field(default=None, max_length=12)
    hourly: bool = False
    surcharge: Surcharge = "none"


class PriceReadOut(BaseModel):
    lines: list[LineIn] = Field(default_factory=list, max_length=MAX_LINES)
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
        label = re.sub(r"\s+", " ", p.label).strip()
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
        lines.append(
            PriceLine(
                id=line_id,
                sheet=sheet.name,
                section=re.sub(r"\s+", " ", p.section).strip(),
                label=label,
                unit=p.unit.strip(),
                quantity=quantity,
                price_cell=price,
                hours_cell=hours,
                rate_cell=rate,
                hourly=p.hourly,
                surcharge=p.surcharge if p.hourly else "none",
            )
        )
    warnings = []
    if dropped:
        warnings.append(
            f"{dropped} ligne{'s' if dropped > 1 else ''} proposée{'s' if dropped > 1 else ''} "
            "par la lecture ne correspondai"
            f"{'ent' if dropped > 1 else 't'} à aucune case à remplir : écartée"
            f"{'s' if dropped > 1 else ''}."
        )
    return lines, warnings


def _split(ref: str) -> tuple[str, int]:
    match = _CELL.match(ref)
    assert match is not None
    return match.group(1), int(match.group(2))


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
    source: Literal["hours", "price", "hourly", "none"]

    @property
    def missing(self) -> bool:
        return self.price_cents is None


@dataclass(frozen=True)
class Priced:
    lines: list[LinePrice]
    total_cents: int
    missing_count: int


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
) -> Priced:
    """``rate_cents``: this dossier's hourly rate, else the company's."""
    rate = rate_cents if rate_cents is not None else rates.hourly_rate_cents
    out: list[LinePrice] = []
    total = 0
    for ln in lines:
        entry = entries.get(ln.id) or {}
        typed = entry.get("price_cents")
        hours = parse_hours(entry.get("hours"))
        price: int | None = None
        source: Literal["hours", "price", "hourly", "none"] = "none"
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
            total += line_total
        out.append(LinePrice(ln.id, hours, used_rate, price, line_total, source))
    return Priced(out, total, sum(1 for p in out if p.missing))


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
        if p.hours is None or ln.hourly:
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
