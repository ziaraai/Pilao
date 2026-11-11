import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog
from tests.api.helpers import signed_in_client
from tests.conftest import Outbox

Factory = Callable[[], TestClient]


def client(make_client: Factory, outbox: Outbox, n: int = 1) -> TestClient:
    return signed_in_client(make_client, outbox, n)


def test_trades_catalog(make_client: Factory, outbox: Outbox) -> None:
    c = client(make_client, outbox)
    trades = {t["code"]: t for t in c.get("/profile/trades").json()}
    assert set(trades) >= {"nettoyage_locaux", "vitrerie", "hygiene"}
    assert "90911300" in trades["vitrerie"]["cpv_codes"]


def test_empty_profile_defaults(make_client: Factory, outbox: Outbox) -> None:
    c = client(make_client, outbox)
    body = c.get("/profile").json()
    assert body["trades"] == [] and body["min_score_alert"] == 60
    assert body["completeness"]["pct"] == 0 and len(body["completeness"]["missing"]) == 9


def test_put_profile_roundtrip_and_normalization(make_client: Factory, outbox: Outbox) -> None:
    c = client(make_client, outbox)
    payload = {
        "trades": ["vitrerie", "vitrerie"],
        "cpv_codes": ["90911300-3", "90911300"],
        "keywords_include": ["vitrerie"],
        "keywords_exclude": ["désamiantage"],
        "departments": ["2a", "75", "974"],
        "min_amount_cents": 1000000,
        "max_amount_cents": 50000000,
        "revenue_y1_cents": 100,
        "revenue_y2_cents": 200,
        "revenue_y3_cents": 300,
        "min_score_alert": 70,
    }
    res = c.put("/profile", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["trades"] == ["vitrerie"] and body["cpv_codes"] == ["90911300"]
    assert body["departments"] == ["2A", "75", "974"]
    assert c.get("/profile").json()["min_score_alert"] == 70


def test_trade_defaults_merge_cpv_and_keywords(make_client: Factory, outbox: Outbox) -> None:
    c = client(make_client, outbox)
    body = c.put(
        "/profile",
        json={"trades": ["hygiene"], "cpv_codes": ["12345678"], "apply_trade_defaults": True},
    ).json()
    assert body["cpv_codes"] == ["12345678", "90920000", "90921000"]
    assert "bionettoyage" in body["keywords_include"]


def test_trade_defaults_never_reinclude_an_excluded_keyword(
    make_client: Factory, outbox: Outbox
) -> None:
    c = client(make_client, outbox)
    body = c.put(
        "/profile",
        json={
            "trades": ["hygiene"],
            "keywords_exclude": ["Désinfection"],
            "apply_trade_defaults": True,
        },
    ).json()
    assert body["keywords_include"] == ["bionettoyage"]
    assert body["keywords_exclude"] == ["Désinfection"]


def test_profile_validation(make_client: Factory, outbox: Outbox) -> None:
    c = client(make_client, outbox)
    bad = [
        {"trades": ["magie"]},
        {"cpv_codes": ["123"]},
        {"departments": ["99"]},
        {"departments": ["00"]},
        {"min_amount_cents": 10, "max_amount_cents": 5},
        {"min_amount_cents": -1},
        {"min_score_alert": 101},
        {"keywords_include": ["nettoyage"], "keywords_exclude": ["Nettoyage"]},
    ]
    for payload in bad:
        assert c.put("/profile", json=payload).status_code == 422, payload


def test_completeness_grows_with_data(make_client: Factory, outbox: Outbox) -> None:
    c = client(make_client, outbox)
    c.put(
        "/profile",
        json={"trades": ["vitrerie"], "apply_trade_defaults": True, "departments": ["75"]},
    )
    pct = c.get("/profile/completeness").json()["pct"]
    assert pct == 15 + 15 + 10  # trades + watch + departments
    c.post("/profile/human-resources", json={"qualification": "Agent de service", "count": 12})
    c.post("/profile/equipment", json={"name": "Autolaveuse", "quantity": 3})
    after = c.get("/profile/completeness").json()
    assert after["pct"] == pct + 10 + 10
    assert "Moyens humains" not in after["missing"] and "Certifications" in after["missing"]
    # the keys say which profile tab to open, in the same order as the labels
    assert "human_resources" not in after["missing_keys"]
    assert after["missing_keys"].index("certifications") == after["missing"].index("Certifications")
    assert c.get("/profile").json()["completeness"]["pct"] == after["pct"]


def test_profile_writes_are_audited(make_client: Factory, outbox: Outbox, db: Session) -> None:
    c = client(make_client, outbox)
    rid = c.post("/profile/equipment", json={"name": "Autolaveuse"}).json()["id"]
    c.put(f"/profile/equipment/{rid}", json={"name": "Autolaveuse autoportée"})
    c.delete(f"/profile/equipment/{rid}")
    logs = db.scalars(select(AuditLog).where(AuditLog.entity == "equipment")).all()
    assert sorted(log.action for log in logs) == ["create", "delete", "update"]
    assert {log.entity_id for log in logs} == {uuid.UUID(rid)}


def test_crud_human_resources(make_client: Factory, outbox: Outbox) -> None:
    c = client(make_client, outbox)
    created = c.post(
        "/profile/human-resources", json={"qualification": "Chef d'équipe", "count": 2}
    )
    assert created.status_code == 201
    rid = created.json()["id"]
    assert (
        c.put(
            f"/profile/human-resources/{rid}", json={"qualification": "Chef d'équipe", "count": 4}
        ).json()["count"]
        == 4
    )
    assert [r["count"] for r in c.get("/profile/human-resources").json()] == [4]
    assert c.delete(f"/profile/human-resources/{rid}").status_code == 204
    assert c.get(f"/profile/human-resources/{rid}").status_code == 404
    assert (
        c.post("/profile/human-resources", json={"qualification": "x", "count": -1}).status_code
        == 422
    )


def test_certification_dates_and_foreign_file_rejected(
    make_client: Factory, outbox: Outbox
) -> None:
    c = client(make_client, outbox)
    ok = c.post("/profile/certifications", json={"name": "ISO 9001", "valid_until": "2027-06-30"})
    assert ok.status_code == 201 and ok.json()["valid_until"] == "2027-06-30"
    ghost = c.post("/profile/certifications", json={"name": "X", "file_id": str(uuid.uuid4())})
    assert ghost.status_code == 422 and ghost.json()["error"]["code"] == "unknown_file"


def test_requires_authentication(make_client: Factory) -> None:
    anon = make_client()
    assert anon.get("/profile").status_code == 401
    assert anon.put("/profile", json={}).status_code == 401
    assert anon.post("/profile/equipment", json={"name": "x"}).status_code == 401


def test_tenancy_isolation_on_every_profile_endpoint(make_client: Factory, outbox: Outbox) -> None:
    a, b = client(make_client, outbox, 1), client(make_client, outbox, 2)
    a.put("/profile", json={"trades": ["vitrerie"], "departments": ["75"]})
    ids = {}
    for path, body in {
        "human-resources": {"qualification": "Agent", "count": 1},
        "equipment": {"name": "Aspirateur"},
        "certifications": {"name": "ISO 14001"},
    }.items():
        ids[path] = b.post(f"/profile/{path}", json=body).json()["id"]

    # A sees none of B's rows and cannot read, change or delete them by id.
    assert a.get("/profile").json()["trades"] == ["vitrerie"]
    assert b.get("/profile").json()["trades"] == []
    for path, item_id in ids.items():
        assert a.get(f"/profile/{path}").json() == []
        assert a.get(f"/profile/{path}/{item_id}").status_code == 404
        assert (
            a.put(
                f"/profile/{path}/{item_id}", json={"name": "x", "qualification": "x", "count": 1}
            ).status_code
            == 404
        )
        assert a.delete(f"/profile/{path}/{item_id}").status_code == 404
        assert b.get(f"/profile/{path}/{item_id}").status_code == 200  # untouched


def test_editing_a_line_keeps_what_the_table_does_not_show(
    make_client: Factory, outbox: Outbox
) -> None:
    """« Modifier » sends the columns of the table only: the attached file, the photos and
    the other fields stay as they were (a PUT changes only the fields it carries)."""
    from tests.api.test_vault import PDF

    c = client(make_client, outbox)
    file_id = c.post("/files", files={"file": ("fiche.pdf", PDF, "application/pdf")}).json()["id"]
    eq = c.post(
        "/profile/equipment",
        json={"name": "Autolaveuse", "quantity": 2, "spec_file_id": file_id},
    ).json()
    cert = c.post("/profile/certifications", json={"name": "ISO 9001", "file_id": file_id}).json()
    ref = c.post(
        "/profile/references",
        json={
            "client_name": "Ville de Lyon",
            "client_type": "public",
            "title": "Nettoyage des écoles",
            "description": "Trois groupes scolaires",
            "photo_file_ids": [file_id],
        },
    ).json()

    edited = c.put(
        f"/profile/equipment/{eq['id']}",
        json={"name": "Autolaveuse Tennant T5", "category": "autolaveuse", "quantity": 3},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["spec_file_id"] == file_id
    assert edited.json()["name"] == "Autolaveuse Tennant T5"
    cert_edit = c.put(f"/profile/certifications/{cert['id']}", json={"name": "ISO 9001:2015"})
    assert cert_edit.json()["file_id"] == file_id
    ref_edit = c.put(
        f"/profile/references/{ref['id']}",
        json={"client_name": "Ville de Lyon", "client_type": "public", "title": "Écoles"},
    )
    assert ref_edit.json()["photo_file_ids"] == [file_id]
    assert ref_edit.json()["description"] == "Trois groupes scolaires"
    # a field sent empty is emptied on purpose
    cleared = c.put(
        f"/profile/equipment/{eq['id']}", json={"name": "Autolaveuse", "quantity": None}
    )
    assert cleared.json()["quantity"] is None and cleared.json()["spec_file_id"] == file_id
