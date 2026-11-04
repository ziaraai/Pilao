"""Excel template and import for company references (US-1.3 CA1).

Hardening: .xlsx only (zip magic bytes), size and row caps, read-only/data-only parsing (no
formula evaluation, no external links followed), every row validated by ``ReferenceIn``.
"""

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import ValidationError

from app.core.errors import ApiError
from app.schemas.profile import ReferenceIn

MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 500

# (field, header shown in the template, required)
COLUMNS: tuple[tuple[str, str, bool], ...] = (
    ("client_name", "Client", True),
    ("client_type", "Type de client (public / privé)", True),
    ("title", "Objet du marché", True),
    ("location", "Lieu", False),
    ("department", "Département", False),
    ("amount", "Montant (€ HT)", False),
    ("year", "Année", False),
    ("duration_months", "Durée (mois)", False),
    ("description", "Description des prestations", False),
    ("cpv_codes", "Codes CPV (séparés par des virgules)", False),
)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


_HEADER_KEYS = {_norm(label): field for field, label, _ in COLUMNS}
# Also accept the short forms people type by hand.
_HEADER_KEYS.update(
    {
        "client": "client_name",
        "objet": "title",
        "montant": "amount",
        "duree": "duration_months",
        "description": "description",
        "cpv": "cpv_codes",
        "type de client": "client_type",
        "departement": "department",
        "codes cpv": "cpv_codes",
        "montant ht": "amount",
        "duree mois": "duration_months",
        "lieu": "location",
        "annee": "year",
    }
)


def build_template() -> bytes:
    wb = Workbook()
    ws = wb.create_sheet("Références", 0)
    wb.remove(wb["Sheet"])
    ws.append([label for _, label, _ in COLUMNS])
    for col, (_, label, _) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="011844")
        ws.column_dimensions[get_column_letter(col)].width = max(18, len(label) + 4)
    help_ws = wb.create_sheet("Mode d'emploi")
    for line in (
        "Une ligne = une référence (un chantier ou un marché réalisé).",
        "Colonnes obligatoires : Client, Type de client, Objet du marché.",
        "Type de client : « public » ou « privé ».",
        "Département : 2 chiffres (75), 2A/2B ou 3 chiffres pour l'outre-mer (974).",
        "Montant : en euros HT, par exemple 125000 ou 125 000,50.",
        "Ne modifiez pas la ligne d'en-tête. 500 lignes maximum par import.",
        "Seules les informations saisies ici seront utilisées dans vos mémoires.",
    ):
        help_ws.append([line])
    help_ws.column_dimensions["A"].width = 100
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@dataclass
class RowResult:
    row: int
    data: ReferenceIn | None = None
    error: str | None = None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _amount_cents(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).replace("\xa0", "").replace(" ", "").replace("€", "").replace(",", ".")
    try:
        euros = Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"montant illisible : « {value} »") from None
    if euros < 0:
        raise ValueError("le montant ne peut pas être négatif")
    return int((euros * 100).quantize(Decimal(1)))


def _int(value: Any, label: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError(f"{label} illisible : « {value} »") from None
    if number != number.to_integral_value():
        raise ValueError(f"{label} doit être un nombre entier")
    return int(number)


def _client_type(value: Any) -> str:
    key = _norm(str(value or ""))
    if key in ("public", "publique"):
        return "public"
    if key in ("prive", "privee", "private"):
        return "private"
    raise ValueError("type de client : « public » ou « privé »")


def _cpv_list(value: Any) -> list[str]:
    return [p for p in re.split(r"[,;\s]+", str(value or "")) if p]


def _department(value: Any) -> str | None:
    s = _text(value)
    if s is None:
        return None
    return s.zfill(2) if s.isdigit() and len(s) == 1 else s  # Excel turns "01" into 1


def _row_to_reference(values: dict[str, Any]) -> ReferenceIn:
    return ReferenceIn(
        client_name=_text(values.get("client_name")) or "",
        client_type=_client_type(values.get("client_type")),
        title=_text(values.get("title")) or "",
        location=_text(values.get("location")),
        department=_department(values.get("department")),
        amount_cents=_amount_cents(values.get("amount")),
        year=_int(values.get("year"), "année"),
        duration_months=_int(values.get("duration_months"), "durée"),
        description=_text(values.get("description")),
        cpv_codes=_cpv_list(values.get("cpv_codes")),
    )


def _friendly(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = str(err["loc"][0]) if err["loc"] else "ligne"
        label = next((lbl for f, lbl, _ in COLUMNS if f == field), field)
        parts.append(f"{label} : {err['msg'].removeprefix('Value error, ')}")
    return " ; ".join(parts)


def parse_workbook(content: bytes) -> tuple[list[RowResult], list[str]]:
    """Return the parsed rows and the names of the columns that were not recognized."""
    if len(content) > MAX_BYTES:
        raise ApiError(413, "file_too_large", "Fichier trop volumineux (5 Mo maximum).")
    if not content.startswith(b"PK") or not zipfile.is_zipfile(io.BytesIO(content)):
        raise ApiError(422, "bad_file", "Le fichier doit être un classeur Excel (.xlsx).")
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
    except Exception:  # noqa: BLE001 - any parser failure on an untrusted file is a 422
        raise ApiError(422, "bad_file", "Impossible de lire ce classeur Excel.") from None
    if header is None:
        raise ApiError(422, "empty_file", "Le classeur est vide.")
    mapping = {
        i: _HEADER_KEYS[_norm(str(h))]
        for i, h in enumerate(header)
        if h and _norm(str(h)) in _HEADER_KEYS
    }
    ignored = [str(h) for i, h in enumerate(header) if h and i not in mapping]
    missing = [lbl for f, lbl, req in COLUMNS if req and f not in mapping.values()]
    if missing:
        raise ApiError(422, "missing_columns", f"Colonnes manquantes : {', '.join(missing)}.")

    results: list[RowResult] = []
    for number, row in enumerate(rows, start=2):
        values = {mapping[i]: v for i, v in enumerate(row) if i in mapping}
        if all(_text(v) is None for v in values.values()):
            continue  # blank line
        if len(results) >= MAX_ROWS:
            raise ApiError(422, "too_many_rows", f"{MAX_ROWS} lignes maximum par import.")
        try:
            results.append(RowResult(number, data=_row_to_reference(values)))
        except ValidationError as exc:
            results.append(RowResult(number, error=_friendly(exc)))
        except ValueError as exc:
            results.append(RowResult(number, error=str(exc)))
    return results, ignored
