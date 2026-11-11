"""Excel import of the staff and equipment lists (US-1.3 CA1, like the references)."""

import io
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog
from tests.api.helpers import signed_in_client
from tests.conftest import Outbox

Factory = Callable[[], TestClient]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
STAFF = ["Qualification", "Nombre", "Précisions"]
EQUIPMENT = ["Matériel", "Type de matériel", "Quantité"]


def workbook(header: list[str], rows: list[list[Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(header)
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def upload(c: TestClient, path: str, content: bytes, dry_run: bool = False) -> Any:
    return c.post(
        f"/profile/{path}/import?dry_run={str(dry_run).lower()}",
        files={"file": ("liste.xlsx", content, XLSX)},
    )


@pytest.mark.parametrize(
    ("path", "sheet", "header", "row"),
    [
        (
            "human-resources",
            "Moyens humains",
            STAFF,
            ["Agent de propreté", 12, "Formés aux gestes"],
        ),
        (
            "equipment",
            "Moyens matériels",
            EQUIPMENT,
            ["Autolaveuse Nilfisk SC450", "autolaveuse", 4],
        ),
    ],
)
def test_the_template_downloads_and_imports_once_filled(
    make_client: Factory, outbox: Outbox, path: str, sheet: str, header: list[str], row: list[Any]
) -> None:
    c = signed_in_client(make_client, outbox)
    res = c.get(f"/profile/{path}/template.xlsx")
    assert res.status_code == 200 and res.headers["content-type"] == XLSX
    assert ".xlsx" in res.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(res.content))
    assert wb.sheetnames == [sheet, "Mode d'emploi"]
    assert [cell.value for cell in wb[sheet][1]] == header
    wb[sheet].append(row)
    out = io.BytesIO()
    wb.save(out)
    report = upload(c, path, out.getvalue()).json()
    assert (report["total"], report["created"], report["errors"], report["skipped"]) == (
        1,
        1,
        [],
        [],
    )
    assert len(c.get(f"/profile/{path}").json()) == 1


def test_staff_rows_are_checked_one_by_one(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    content = workbook(
        STAFF,
        [
            ["Agent de propreté", 12, "Formés aux gestes et postures"],
            ["Chef d'équipe", "3", None],
            [None, None, None],  # a blank line is skipped, not reported
            ["Responsable d'exploitation", "un", None],
            [None, 4, "sans qualification"],
            ["Laveur de vitres", -2, None],
            ["Agent polyvalent", 2.5, None],
        ],
    )
    preview = upload(c, "human-resources", content, dry_run=True).json()
    assert (preview["dry_run"], preview["created"], preview["total"]) == (True, 0, 6)
    assert c.get("/profile/human-resources").json() == []

    report = upload(c, "human-resources", content).json()
    assert (report["total"], report["created"]) == (6, 2)
    assert report["errors"] == [
        {"row": 5, "message": "effectif illisible : « un »"},
        {"row": 6, "message": "Qualification : champ obligatoire"},
        {"row": 7, "message": "Nombre : doit être au moins 0"},
        {"row": 8, "message": "effectif doit être un nombre entier"},
    ]
    staff = {h["qualification"]: h for h in c.get("/profile/human-resources").json()}
    assert staff["Agent de propreté"]["count"] == 12
    assert staff["Agent de propreté"]["description"] == "Formés aux gestes et postures"
    assert staff["Chef d'équipe"]["count"] == 3
    assert c.get("/profile/completeness").json()["pct"] > 0
    assert db.scalar(select(AuditLog.meta).where(AuditLog.entity == "human_resource")) == {
        "created": 2,
        "skipped": 0,
    }


def test_a_line_already_in_the_profile_is_skipped_not_doubled(
    make_client: Factory, outbox: Outbox
) -> None:
    c = signed_in_client(make_client, outbox)
    assert (
        c.post("/profile/equipment", json={"name": "Autolaveuse Nilfisk SC450"}).status_code == 201
    )
    content = workbook(
        EQUIPMENT,
        [
            ["autolaveuse  nilfisk sc450", "autolaveuse", 4],  # same machine, typed differently
            ["Monobrosse Taski Ergodisc", "monobrosse", 6],
            ["Monobrosse Taski Ergodisc", "monobrosse", 6],  # twice in the file
            ["Aspirateur Numatic", None, None],
        ],
    )
    report = upload(c, "equipment", content).json()
    assert (report["total"], report["created"], report["errors"]) == (4, 2, [])
    assert report["skipped"] == [
        {"row": 2, "message": "déjà dans votre profil : « Autolaveuse Nilfisk SC450 »"},
        {"row": 4, "message": "déjà plus haut dans le fichier : « Monobrosse Taski Ergodisc »"},
    ]
    names = sorted(e["name"] for e in c.get("/profile/equipment").json())
    assert names == ["Aspirateur Numatic", "Autolaveuse Nilfisk SC450", "Monobrosse Taski Ergodisc"]
    again = upload(c, "equipment", content).json()  # the same file twice: nothing doubled
    assert again["created"] == 0 and len(again["skipped"]) == 4


def test_short_headers_and_the_old_category_header_are_understood(
    make_client: Factory, outbox: Outbox
) -> None:
    c = signed_in_client(make_client, outbox)
    content = workbook(["materiel", "Catégorie", "qte", "Prix"], [["Nacelle", "nacelle", "1"]])
    report = upload(c, "equipment", content).json()
    assert (report["created"], report["ignored_columns"]) == (1, ["Prix"])
    (machine,) = c.get("/profile/equipment").json()
    assert (machine["name"], machine["category"], machine["quantity"]) == ("Nacelle", "nacelle", 1)
    staff = workbook(["Poste", "Effectif"], [["Agent de propreté", 24]])
    assert upload(c, "human-resources", staff).json()["created"] == 1


def test_a_sheet_without_the_required_columns_or_not_excel_is_refused(
    make_client: Factory, outbox: Outbox
) -> None:
    c = signed_in_client(make_client, outbox)
    missing = upload(c, "human-resources", workbook(["Précisions"], [["x"]]))
    assert missing.status_code == 422
    assert missing.json()["error"]["message"] == "Colonnes manquantes : Qualification, Nombre."
    not_excel = upload(c, "equipment", b"pas un classeur")
    assert not_excel.status_code == 422 and not_excel.json()["error"]["code"] == "bad_file"


def test_each_company_imports_into_its_own_profile(make_client: Factory, outbox: Outbox) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    upload(a, "human-resources", workbook(STAFF, [["Agent de propreté", 12, None]]))
    assert b.get("/profile/human-resources").json() == []
    # a line in another company's profile is not a duplicate here
    assert (
        upload(b, "human-resources", workbook(STAFF, [["Agent de propreté", 3, None]])).json()[
            "created"
        ]
        == 1
    )


def test_references_report_no_skipped_lines(make_client: Factory, outbox: Outbox) -> None:
    """The references keep their behaviour; their report only gains an empty « skipped »."""
    c = signed_in_client(make_client, outbox)
    header = ["Client", "Type de client (public / privé)", "Objet du marché"]
    res = c.post(
        "/profile/references/import",
        files={"file": ("r.xlsx", workbook(header, [["Mairie", "public", "Écoles"]]), XLSX)},
    )
    assert res.json()["created"] == 1 and res.json()["skipped"] == []


def test_import_needs_a_session(make_client: Factory) -> None:
    c = make_client()
    assert c.get("/profile/equipment/template.xlsx").status_code == 401
    assert upload(c, "human-resources", workbook(STAFF, [])).status_code == 401
