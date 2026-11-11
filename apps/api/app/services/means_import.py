"""Excel template and import for the staff and equipment lists of the profile (US-1.3 CA1).

Many companies already keep these lists in a spreadsheet: they fill the template (or keep
their own headers, short forms are understood) and import it. A line already in the profile
(same qualification, same machine: case, accents and spacing aside) is skipped and reported,
so importing the same file twice doubles nothing.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.schemas.profile import EquipmentIn, HumanResourceIn
from app.services.sheet_import import RowResult, Sheet, integer, norm, present, text


def _staff(values: dict[str, Any]) -> HumanResourceIn:
    return HumanResourceIn(
        **present(
            qualification=text(values.get("qualification")),
            count=integer(values.get("count"), "effectif"),
            description=text(values.get("description")),
        )
    )


def _equipment(values: dict[str, Any]) -> EquipmentIn:
    return EquipmentIn(
        **present(
            name=text(values.get("name")),
            category=text(values.get("category")),
            quantity=integer(values.get("quantity"), "quantité"),
        )
    )


STAFF: Sheet[HumanResourceIn] = Sheet(
    title="Moyens humains",
    columns=(
        ("qualification", "Qualification", True),
        ("count", "Nombre", True),
        ("description", "Précisions", False),
    ),
    to_model=_staff,
    help_lines=(
        "Une ligne = une qualification et le nombre de personnes (ex. Agent de propreté, 12).",
        "Colonnes obligatoires : Qualification, Nombre.",
        "Précisions : formations, habilitations, ancienneté… (facultatif).",
        "Une qualification déjà présente dans votre profil n'est pas ajoutée une seconde fois.",
        "Ne modifiez pas la ligne d'en-tête. 500 lignes maximum par import.",
        "Seules les informations saisies ici seront utilisées dans vos mémoires.",
    ),
    aliases={
        "poste": "qualification",
        "fonction": "qualification",
        "effectif": "count",
        "nb": "count",
        "description": "description",
        "commentaire": "description",
    },
)

EQUIPMENT: Sheet[EquipmentIn] = Sheet(
    title="Moyens matériels",
    columns=(
        ("name", "Matériel", True),
        ("category", "Type de matériel", False),
        ("quantity", "Quantité", False),
    ),
    to_model=_equipment,
    help_lines=(
        "Une ligne = un matériel (ex. Autolaveuse Nilfisk SC450, autolaveuse, 4).",
        "Colonne obligatoire : Matériel (le nom ou le modèle de la machine).",
        (
            "Type de matériel : autolaveuse, monobrosse, aspirateur, nacelle… Il sert à"
            " regrouper votre matériel par type dans la liste des moyens matériels du dossier."
        ),
        "Quantité : un nombre entier (facultatif).",
        "Un matériel déjà présent dans votre profil n'est pas ajouté une seconde fois.",
        "Ne modifiez pas la ligne d'en-tête. 500 lignes maximum par import.",
    ),
    aliases={
        "materiel": "name",
        "machine": "name",
        "designation": "name",
        "nom": "name",
        "categorie": "category",
        "type": "category",
        "qte": "quantity",
        "nombre": "quantity",
    },
)


@dataclass
class Sorted:
    """The rows of an import, once checked against the profile and against each other."""

    new: list[RowResult[Any]]
    skipped: list[RowResult[Any]]  # ``error`` holds the reason, shown as a note
    errors: list[RowResult[Any]]


def sort_rows[M: BaseModel](
    rows: list[RowResult[M]], existing: Sequence[str], name_field: str
) -> Sorted:
    """Split the parsed rows into lines to add, duplicates to skip and lines in error."""
    known = {norm(name): name for name in existing}
    seen: set[str] = set()
    out = Sorted(new=[], skipped=[], errors=[])
    for r in rows:
        if r.data is None:
            out.errors.append(r)
            continue
        name = str(getattr(r.data, name_field))
        key = norm(name)
        if key in known:
            out.skipped.append(RowResult(r.row, error=f"déjà dans votre profil : « {known[key]} »"))
        elif key in seen:
            out.skipped.append(
                RowResult(r.row, error=f"déjà plus haut dans le fichier : « {name} »")
            )
        else:
            seen.add(key)
            out.new.append(r)
    return out
