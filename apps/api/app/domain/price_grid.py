"""The buyer's price file as a grid of cells (ADR-049): what the AI reads, what the server checks.

Two readings of the same workbook: the cells as written (a formula stays « =B5 ») and the
results Excel cached the last time it saved the file (the quantities may be formulas).
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from openpyxl import load_workbook

MAX_CELLS = 6000  # about 60 000 characters: a big DPGF fits, an absurd one is cut
_TEXT_LIMIT = 150


class PriceFileError(Exception):
    """Not a readable Excel workbook."""


@dataclass(frozen=True)
class Cell:
    raw: Any  # the value as written; a formula is a string starting with « = »
    cached: Any  # the last computed result saved in the file (None when unknown)

    @property
    def formula(self) -> bool:
        return isinstance(self.raw, str) and self.raw.startswith("=")


@dataclass
class Sheet:
    name: str
    hidden: bool
    cells: dict[str, Cell] = field(default_factory=dict)


def _plain(value: Any) -> Any:
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if value is None or isinstance(value, str | int | float | bool):
        return value
    text = getattr(value, "text", None)  # an array formula keeps its text here
    return text if isinstance(text, str) else str(value)


def read_workbook(data: bytes) -> list[Sheet]:
    try:
        written = load_workbook(io.BytesIO(data), data_only=False)
        computed = load_workbook(io.BytesIO(data), data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
        raise PriceFileError("Ce fichier n'est pas un classeur Excel lisible.") from exc
    sheets: list[Sheet] = []
    for ws in written.worksheets:
        values = computed[ws.title]
        sheet = Sheet(ws.title, ws.sheet_state != "visible")
        for row in ws.iter_rows():
            for cell in row:
                raw = _plain(cell.value)
                if raw is None or raw == "":
                    continue
                sheet.cells[cell.coordinate] = Cell(raw, _plain(values[cell.coordinate].value))
        sheets.append(sheet)
    return sheets


def _show(raw: Any) -> str:
    if isinstance(raw, str) and not raw.startswith("="):
        text = re.sub(r"\s+", " ", raw).strip()
        if len(text) > _TEXT_LIMIT:
            text = text[: _TEXT_LIMIT - 1] + "…"
        return f"« {text} »"
    return str(raw)


def _row_of(ref: str) -> int:
    return int(re.sub(r"^[A-Z]+", "", ref))


def grid_text(sheets: list[Sheet], max_cells: int = MAX_CELLS) -> tuple[str, bool]:
    """The visible sheets, one line per row (« B5: 0 | H5: =B5 »). Returns (text, cut)."""
    lines: list[str] = []
    left = max_cells
    cut = False
    for sheet in sheets:
        if sheet.hidden:
            continue
        lines.append(f"=== Feuille « {sheet.name} » ===")
        rows: dict[int, list[str]] = {}
        for ref, cell in sheet.cells.items():
            if left <= 0:
                cut = True
                break
            rows.setdefault(_row_of(ref), []).append(f"{ref}: {_show(cell.raw)}")
            left -= 1
        lines.extend(" | ".join(parts) for _, parts in sorted(rows.items()))
        if cut:
            break
    return "\n".join(lines), cut
