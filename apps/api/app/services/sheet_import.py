"""Excel templates and imports of the profile lists: references, staff, equipment (US-1.3).

One generic reader, one :class:`Sheet` per list. Hardening: .xlsx only (zip magic bytes),
size and row caps, read-only/data-only parsing (no formula evaluation, no external links
followed), every row validated by the list's Pydantic schema.
"""

import io
import re
import unicodedata
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, ValidationError

from app.core.errors import ApiError

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 500
# Physical rows read (blank lines included) and header cells read, whatever the sheet claims.
MAX_SCANNED_ROWS = 20 * MAX_ROWS
MAX_COLUMNS = 100


def norm(text: str) -> str:
    """Lowercase, without accents, words separated by single spaces: for headers and names."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


@dataclass(frozen=True)
class Sheet[T: BaseModel]:
    """One importable list."""

    title: str  # the template's sheet name
    columns: tuple[tuple[str, str, bool], ...]  # (field, header shown, required)
    to_model: Callable[[dict[str, Any]], T]  # a row's values by field -> the validated line
    help_lines: tuple[str, ...]
    aliases: dict[str, str] = field(default_factory=dict)  # short headers typed by hand
    model_to_column: dict[str, str] = field(default_factory=dict)  # schema field -> column

    def header_keys(self) -> dict[str, str]:
        keys = {norm(label): f for f, label, _ in self.columns}
        keys.update({norm(alias): f for alias, f in self.aliases.items()})
        return keys


@dataclass
class RowResult[T: BaseModel]:
    row: int
    data: T | None = None
    error: str | None = None


def build_template(sheet: Sheet[Any]) -> bytes:
    wb = Workbook()
    ws = wb.create_sheet(sheet.title, 0)
    wb.remove(wb["Sheet"])
    ws.append([label for _, label, _ in sheet.columns])
    for col, (_, label, _) in enumerate(sheet.columns, start=1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="011844")
        ws.column_dimensions[get_column_letter(col)].width = max(18, len(label) + 4)
    help_ws = wb.create_sheet("Mode d'emploi")
    for line in sheet.help_lines:
        help_ws.append([line])
    help_ws.column_dimensions["A"].width = 100
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# --- Cell readers (a ``ValueError`` becomes the row's error message) -----------------------


def text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


# Far above any real amount, year or duration; keeps int()/quantize() cheap and in range
# ("1e999999999" would otherwise build a billion-digit integer or overflow the context).
_MAX_ADJUSTED_EXPONENT = 15


def decimal(raw: str, value: Any, label: str) -> Decimal:
    """Parse a finite, reasonably sized decimal, or raise a ``ValueError`` for the row."""
    try:
        number = Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"{label} illisible : « {value} »") from None
    if not number.is_finite() or number.adjusted() > _MAX_ADJUSTED_EXPONENT:
        raise ValueError(f"{label} illisible : « {value} »")
    return number


def integer(value: Any, label: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    number = decimal(str(value).strip().replace(",", "."), value, label)
    if number != number.to_integral_value():
        raise ValueError(f"{label} doit être un nombre entier")
    return int(number)


def present(**values: Any) -> dict[str, Any]:
    """The values that were filled in: an empty required cell is then « champ obligatoire »."""
    return {k: v for k, v in values.items() if v is not None}


# --- Errors in French ----------------------------------------------------------------------


def _friendly(exc: ValidationError, sheet: Sheet[Any]) -> str:
    parts = []
    for err in exc.errors():
        name = str(err["loc"][0]) if err["loc"] else "ligne"
        name = sheet.model_to_column.get(name, name)
        label = next((lbl for f, lbl, _ in sheet.columns if f == name), name)
        parts.append(f"{label} : {_french(err)}")
    return " ; ".join(parts)


def _french(err: Any) -> str:
    """The user reads this report: Pydantic's English messages are translated."""
    msg = str(err["msg"])
    if msg.startswith("Value error, "):
        return msg.removeprefix("Value error, ")  # our own validators speak French
    kind, ctx = str(err.get("type", "")), err.get("ctx") or {}
    if kind == "string_too_short":
        return (
            "champ obligatoire"
            if ctx.get("min_length") == 1
            else f"{ctx.get('min_length')} caractères minimum"
        )
    if kind == "string_too_long":
        return f"{ctx.get('max_length')} caractères maximum"
    if kind in ("greater_than_equal", "greater_than"):
        return f"doit être au moins {ctx.get('ge', ctx.get('gt'))}"
    if kind in ("less_than_equal", "less_than"):
        return f"doit être au plus {ctx.get('le', ctx.get('lt'))}"
    if kind == "missing":
        return "champ obligatoire"
    return "valeur invalide"


# --- Reading -------------------------------------------------------------------------------


def parse_workbook[T: BaseModel](
    content: bytes, sheet: Sheet[T]
) -> tuple[list[RowResult[T]], list[str]]:
    """Return the parsed rows and the names of the columns that were not recognized."""
    if len(content) > MAX_BYTES:
        raise ApiError(413, "file_too_large", "Fichier trop volumineux (5 Mo maximum).")
    if not content.startswith(b"PK") or not zipfile.is_zipfile(io.BytesIO(content)):
        raise ApiError(422, "bad_file", "Le fichier doit être un classeur Excel (.xlsx).")
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - any parser failure on an untrusted file is a 422
        raise ApiError(422, "bad_file", "Impossible de lire ce classeur Excel.") from None
    try:
        return _parse_sheet(wb.worksheets[0], sheet)
    except ApiError:
        raise
    except Exception:  # noqa: BLE001 - rows are parsed lazily: a corrupt row fails here
        raise ApiError(422, "bad_file", "Impossible de lire ce classeur Excel.") from None
    finally:
        wb.close()


def _parse_sheet[T: BaseModel](ws: Any, sheet: Sheet[T]) -> tuple[list[RowResult[T]], list[str]]:
    header = next(ws.iter_rows(max_row=1, max_col=MAX_COLUMNS, values_only=True), None)
    if header is None:
        raise ApiError(422, "empty_file", "Le classeur est vide.")
    keys = sheet.header_keys()
    mapping = {i: keys[norm(str(h))] for i, h in enumerate(header) if h and norm(str(h)) in keys}
    ignored = [str(h) for i, h in enumerate(header) if h and i not in mapping]
    missing = [lbl for f, lbl, req in sheet.columns if req and f not in mapping.values()]
    if missing:
        raise ApiError(422, "missing_columns", f"Colonnes manquantes : {', '.join(missing)}.")

    results: list[RowResult[T]] = []
    # Only the recognized columns are read, and blank lines count toward a physical cap:
    # a few kilobytes of zipped XML can otherwise expand into millions of empty rows/cells.
    rows = ws.iter_rows(min_row=2, max_col=max(mapping) + 1, values_only=True)
    for number, row in enumerate(rows, start=2):
        if number > MAX_SCANNED_ROWS + 1:
            raise ApiError(422, "too_many_rows", f"{MAX_ROWS} lignes maximum par import.")
        values = {mapping[i]: v for i, v in enumerate(row) if i in mapping}
        if all(text(v) is None for v in values.values()):
            continue  # blank line
        if len(results) >= MAX_ROWS:
            raise ApiError(422, "too_many_rows", f"{MAX_ROWS} lignes maximum par import.")
        try:
            results.append(RowResult(number, data=sheet.to_model(values)))
        except ValidationError as exc:
            results.append(RowResult(number, error=_friendly(exc, sheet)))
        except ValueError as exc:
            results.append(RowResult(number, error=str(exc)))
    return results, ignored
