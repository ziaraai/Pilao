"""Excel template and import for company references (US-1.3 CA1).

The reading is shared with the staff and equipment lists (``sheet_import``); this module
holds what is particular to references: the columns, client type, amount, CPV codes.
"""

import re
from decimal import Decimal
from typing import Any

from app.schemas.profile import ReferenceIn
from app.services.sheet_import import (
    MAX_BYTES,
    MAX_ROWS,
    MAX_SCANNED_ROWS,
    RowResult,
    Sheet,
    decimal,
    integer,
    norm,
    text,
)
from app.services.sheet_import import build_template as _build
from app.services.sheet_import import parse_workbook as _parse

__all__ = ["MAX_BYTES", "MAX_ROWS", "MAX_SCANNED_ROWS", "build_template", "parse_workbook"]

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


def _amount_cents(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).replace("\xa0", "").replace(" ", "").replace("€", "").replace(",", ".")
    euros = decimal(raw, value, "montant")
    if euros < 0:
        raise ValueError("le montant ne peut pas être négatif")
    return int((euros * 100).quantize(Decimal(1)))


def _client_type(value: Any) -> str:
    key = norm(str(value or ""))
    if key in ("public", "publique"):
        return "public"
    if key in ("prive", "privee", "private"):
        return "private"
    raise ValueError("type de client : « public » ou « privé »")


def _cpv_list(value: Any) -> list[str]:
    return [p for p in re.split(r"[,;\s]+", str(value or "")) if p]


def _department(value: Any) -> str | None:
    s = text(value)
    if s is None:
        return None
    return s.zfill(2) if s.isdigit() and len(s) == 1 else s  # Excel turns "01" into 1


def _row_to_reference(values: dict[str, Any]) -> ReferenceIn:
    return ReferenceIn(
        client_name=text(values.get("client_name")) or "",
        client_type=_client_type(values.get("client_type")),
        title=text(values.get("title")) or "",
        location=text(values.get("location")),
        department=_department(values.get("department")),
        amount_cents=_amount_cents(values.get("amount")),
        year=integer(values.get("year"), "année"),
        duration_months=integer(values.get("duration_months"), "durée"),
        description=text(values.get("description")),
        cpv_codes=_cpv_list(values.get("cpv_codes")),
    )


REFERENCES: Sheet[ReferenceIn] = Sheet(
    title="Références",
    columns=COLUMNS,
    to_model=_row_to_reference,
    help_lines=(
        "Une ligne = une référence (un chantier ou un marché réalisé).",
        "Colonnes obligatoires : Client, Type de client, Objet du marché.",
        "Type de client : « public » ou « privé ».",
        "Département : 2 chiffres (75), 2A/2B ou 3 chiffres pour l'outre-mer (974).",
        "Montant : en euros HT, par exemple 125000 ou 125 000,50.",
        "Ne modifiez pas la ligne d'en-tête. 500 lignes maximum par import.",
        "Seules les informations saisies ici seront utilisées dans vos mémoires.",
    ),
    # Also accept the short forms people type by hand.
    aliases={
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
    },
    model_to_column={"amount_cents": "amount"},
)


def build_template() -> bytes:
    return _build(REFERENCES)


def parse_workbook(content: bytes) -> tuple[list[RowResult[ReferenceIn]], list[str]]:
    return _parse(content, REFERENCES)
