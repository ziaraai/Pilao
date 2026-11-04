import io
import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from app.services.reference_import import MAX_ROWS
from tests.api.helpers import signed_in_client
from tests.conftest import Outbox

Factory = Callable[[], TestClient]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEADER = [
    "Client",
    "Type de client (public / privé)",
    "Objet du marché",
    "Lieu",
    "Département",
    "Montant (€ HT)",
    "Année",
    "Durée (mois)",
    "Description des prestations",
    "Codes CPV",
]


def workbook(rows: list[list[Any]], header: list[str] | None = HEADER) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    if header is not None:
        ws.append(header)
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def upload(c: TestClient, content: bytes, dry_run: bool = False, name: str = "refs.xlsx") -> Any:
    return c.post(
        f"/profile/references/import?dry_run={str(dry_run).lower()}",
        files={"file": (name, content, XLSX)},
    )


GOOD = [
    "Mairie de Lyon",
    "public",
    "Nettoyage des écoles",
    "Lyon",
    69,
    "125 000,50",
    2023,
    12,
    "Entretien quotidien",
    "90919300, 90911200",
]


def test_template_is_a_valid_workbook_matching_the_importer(
    make_client: Factory, outbox: Outbox
) -> None:
    c = signed_in_client(make_client, outbox)
    res = c.get("/profile/references/template.xlsx")
    assert res.status_code == 200 and res.headers["content-type"] == XLSX
    wb = load_workbook(io.BytesIO(res.content))
    assert wb.sheetnames == ["Références", "Mode d'emploi"]
    # The untouched template, filled with one row, must be importable.
    sheet = wb["Références"]
    sheet.append(GOOD)
    out = io.BytesIO()
    wb.save(out)
    assert upload(c, out.getvalue()).json()["created"] == 1


def test_crud_reference_and_completeness(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    body = {
        "client_name": "Hôpital X",
        "client_type": "public",
        "title": "Bionettoyage",
        "department": "69",
        "amount_cents": 5000000,
        "year": 2022,
        "cpv_codes": ["90921000"],
    }
    created = c.post("/profile/references", json=body)
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    body["title"] = "Bionettoyage bloc opératoire"
    assert c.put(f"/profile/references/{rid}", json=body).json()["title"].endswith("opératoire")
    assert c.get("/profile/completeness").json()["pct"] == 0  # 3 references are required
    for i in range(2):
        c.post("/profile/references", json={**body, "title": f"R{i}"})
    assert c.get("/profile/completeness").json()["pct"] == 15
    assert c.delete(f"/profile/references/{rid}").status_code == 204
    assert c.get(f"/profile/references/{rid}").status_code == 404


def test_reference_validation(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    base = {"client_name": "A", "client_type": "public", "title": "T"}
    for patch in (
        {"client_type": "ong"},
        {"year": 1800},
        {"amount_cents": -5},
        {"department": "XX"},
        {"cpv_codes": ["abc"]},
        {"title": "  "},
    ):
        assert c.post("/profile/references", json={**base, **patch}).status_code == 422, patch
    ghost = c.post("/profile/references", json={**base, "photo_file_ids": [str(uuid.uuid4())]})
    assert ghost.status_code == 422 and ghost.json()["error"]["code"] == "unknown_file"


def test_import_converts_values(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    report = upload(
        c,
        workbook(
            [GOOD, ["SCI Les Pins", "Privé", "Vitrerie", None, 1, 800, None, None, None, None]]
        ),
    ).json()
    assert report == {
        "dry_run": False,
        "total": 2,
        "created": 2,
        "errors": [],
        "ignored_columns": [],
    }
    refs = {r["client_name"]: r for r in c.get("/profile/references").json()}
    lyon = refs["Mairie de Lyon"]
    assert lyon["amount_cents"] == 12500050 and lyon["department"] == "69"
    assert lyon["cpv_codes"] == ["90919300", "90911200"] and lyon["year"] == 2023
    pins = refs["SCI Les Pins"]
    assert (
        pins["client_type"] == "private"
        and pins["department"] == "01"
        and pins["amount_cents"] == 80000
    )


def test_import_reports_bad_rows_but_keeps_good_ones(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    rows = [
        GOOD,
        ["", "public", "Sans client", None, None, None, None, None, None, None],
        ["B", "autre", "Type inconnu", None, None, None, None, None, None, None],
        ["C", "public", "Montant faux", None, None, "beaucoup", None, None, None, None],
        [None] * 10,  # blank line is ignored, not an error
        ["D", "public", "Dépt faux", None, "ZZ", None, 2020, None, None, None],
    ]
    report = upload(c, workbook(rows)).json()
    assert report["total"] == 5 and report["created"] == 1
    assert [e["row"] for e in report["errors"]] == [3, 4, 5, 7]
    assert "montant" in report["errors"][2]["message"].lower()
    assert len(c.get("/profile/references").json()) == 1


def test_import_dry_run_saves_nothing(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    report = upload(c, workbook([GOOD]), dry_run=True).json()
    assert report["dry_run"] and report["created"] == 0 and report["total"] == 1
    assert c.get("/profile/references").json() == []


def test_import_accepts_short_headers_and_any_order(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    content = workbook(
        [["Objet X", "Client Y", "public"]], header=["Objet", "Client", "Type de client"]
    )
    assert upload(c, content).json()["created"] == 1


def test_import_rejects_bad_files(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    assert (
        upload(c, b"client,type\nA,public\n", name="refs.csv").json()["error"]["code"] == "bad_file"
    )
    assert upload(c, b"PK\x03\x04 not really a zip").json()["error"]["code"] == "bad_file"
    assert (
        upload(c, workbook([GOOD], header=["Foo", "Bar"])).json()["error"]["code"]
        == "missing_columns"
    )
    assert upload(c, workbook([], header=None)).status_code == 422
    big = workbook([["C", "public", f"T{i}"] + [None] * 7 for i in range(MAX_ROWS + 1)])
    assert upload(c, big).json()["error"]["code"] == "too_many_rows"
    assert c.get("/profile/references").json() == []


def test_import_rejects_oversized_file(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    res = upload(c, b"PK" + b"0" * (5 * 1024 * 1024 + 10))
    assert res.status_code == 413


def test_formulas_are_not_evaluated_or_trusted(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    rows = [
        ["=1+1", "public", '=HYPERLINK("http://evil")', None, None, None, None, None, None, None]
    ]
    assert upload(c, workbook(rows)).json()["total"] == 1  # stored as plain text, never executed


def test_references_requires_auth_and_is_tenant_isolated(
    make_client: Factory, outbox: Outbox
) -> None:
    anon = make_client()
    assert anon.get("/profile/references").status_code == 401
    assert anon.get("/profile/references/template.xlsx").status_code == 401
    assert (
        anon.post("/profile/references/import", files={"file": ("a.xlsx", b"x", XLSX)}).status_code
        == 401
    )

    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    upload(b, workbook([GOOD]))
    other_id = b.get("/profile/references").json()[0]["id"]
    assert a.get("/profile/references").json() == []
    assert a.get(f"/profile/references/{other_id}").status_code == 404
    assert a.delete(f"/profile/references/{other_id}").status_code == 404
    assert b.get(f"/profile/references/{other_id}").status_code == 200


def test_unknown_columns_are_reported_not_silently_dropped(
    make_client: Factory, outbox: Outbox
) -> None:
    c = signed_in_client(make_client, outbox)
    header = [*HEADER, "Contact acheteur"]
    report = upload(c, workbook([[*GOOD, "M. Martin"]], header=header)).json()
    assert report["created"] == 1 and report["ignored_columns"] == ["Contact acheteur"]
