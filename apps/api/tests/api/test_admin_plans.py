"""Administration, lot 4: plans and action prices (spec §3.1, §5.2)."""

import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AiCall, CreditEntry, Organization, Plan
from tests.api.helpers import signed_in_client
from tests.api.test_admin_accounts import admin, journal, org_id_of
from tests.api.test_modules import set_modules
from tests.conftest import Outbox

REAL_CREDITS = True
Factory = Callable[[], TestClient]


def body(**kw: Any) -> dict[str, Any]:
    return {
        "name": "Essentiel",
        "description": "La veille seule.",
        "modules": ["veille"],
        "monthly_credits": 20,
        "welcome_credits": 0,
        "price_note": "29 € HT par mois",
        **kw,
    }


def plan_id(db: Session, name: str) -> str:
    return str(db.scalars(select(Plan.id).where(Plan.name == name)).one())


def modules_of(db: Session, email: str) -> list[str]:
    db.expire_all()
    return list(db.get_one(Organization, uuid.UUID(org_id_of(db, email))).modules)


def test_create_and_list(make_client: Factory, db: Session) -> None:
    client, _, _ = admin(make_client, db)
    res = client.post("/admin/plans", json=body())
    assert res.status_code == 201, res.text
    p = res.json()
    assert (p["name"], p["modules"], p["monthly_credits"], p["price_note"]) == (
        "Essentiel",
        ["veille"],
        20,
        "29 € HT par mois",
    )
    assert (p["is_default"], p["archived"], p["organizations"]) == (False, False, 0)
    assert [x["name"] for x in client.get("/admin/plans").json()] == [
        "Découverte",
        "Essentiel",
        "Pilote",
    ]
    dup = client.post("/admin/plans", json=body(name=" essentiel "))
    assert dup.status_code == 409
    assert dup.json()["error"]["message"] == "Une formule porte déjà ce nom."
    assert client.post("/admin/plans", json=body(name="X", modules=["crm"])).status_code == 422
    assert client.post("/admin/plans", json=body(name="Y", monthly_credits=-1)).status_code == 422
    assert client.post("/admin/plans", json=body(name="")).status_code == 422
    [line] = journal(db, "plan_created")
    assert line.meta == {"name": "Essentiel"}


def test_editing_applies_to_its_companies_and_keeps_exceptions(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    signed_in_client(make_client, outbox)  # « Découverte »: both modules
    signed_in_client(make_client, outbox, 2)
    set_modules(db, "user2@example.fr", ["reponse"])  # an exception: no watch
    client, _, _ = admin(make_client, db)
    discovery = plan_id(db, "Découverte")

    res = client.put(
        f"/admin/plans/{discovery}",
        json=body(name="Découverte", modules=["veille"], monthly_credits=0, welcome_credits=7),
    )
    assert res.status_code == 200, res.text
    assert res.json()["organizations_affected"] == 2
    assert res.json()["plan"]["modules"] == ["veille"]
    assert modules_of(db, "user1@example.fr") == ["veille"]
    assert modules_of(db, "user2@example.fr") == []  # « Réponse » removed, its exception kept
    [line] = journal(db, "plan_updated")
    assert line.meta == {"name": "Découverte", "organizations": 2}


def test_one_default_and_archiving(make_client: Factory, db: Session) -> None:
    client, _, _ = admin(make_client, db)
    essential = client.post("/admin/plans", json=body()).json()["id"]
    assert client.put(f"/admin/plans/{essential}/default").json()["is_default"] is True
    assert [p["name"] for p in client.get("/admin/plans").json() if p["is_default"]] == [
        "Essentiel"
    ]
    refused = client.post(f"/admin/plans/{essential}/archive")
    assert refused.status_code == 409
    assert refused.json()["error"]["message"] == "Choisissez d'abord une autre formule par défaut."

    client.put(f"/admin/plans/{plan_id(db, 'Découverte')}/default")
    assert client.post(f"/admin/plans/{essential}/archive").json()["archived"] is True
    archived = client.put(f"/admin/plans/{essential}/default")
    assert archived.status_code == 409
    assert archived.json()["error"]["message"] == "Cette formule est archivée."
    assert client.post(f"/admin/plans/{essential}/unarchive").json()["archived"] is False
    unknown = client.post(f"/admin/plans/{uuid.uuid4()}/archive")
    assert unknown.status_code == 404 and unknown.json()["error"]["message"] == "Formule inconnue."
    assert [
        len(journal(db, a)) for a in ("plan_default_set", "plan_archived", "plan_unarchived")
    ] == [
        2,
        1,
        1,
    ]


def test_action_prices_and_their_real_cost(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    org = uuid.UUID(org_id_of(db, "user1@example.fr"))
    paid = [
        CreditEntry(org_id=org, kind="charge", action="dce_analysis", extra=-2, month=None)
        for _ in range(2)
    ]
    db.add_all(paid)
    db.flush()
    db.add(
        CreditEntry(org_id=org, kind="refund", action="dce_analysis", extra=2, refund_of=paid[0].id)
    )
    db.add(AiCall(org_id=org, task="dce_extraction", model="m", cost_eur=Decimal("0.30")))
    db.commit()
    client, _, _ = admin(make_client, db)

    rows = {r["action"]: r for r in client.get("/admin/credit-prices").json()}
    assert list(rows) == [
        "dce_analysis",
        "memoir_generation",
        "chapter_regeneration",
        "profile_prefill",
    ]
    analysis = rows["dce_analysis"]
    assert (
        analysis["name"],
        analysis["module"],
        analysis["credits"],
        analysis["default_credits"],
    ) == (
        "Analyse du DCE",
        "reponse",
        2,
        2,
    )
    assert analysis["uses_30d"] == 1 and Decimal(analysis["avg_cost_30d"]) == Decimal("0.30")
    assert rows["memoir_generation"]["uses_30d"] == 0
    assert rows["memoir_generation"]["avg_cost_30d"] is None

    res = client.put("/admin/credit-prices/dce_analysis", json={"credits": 3})
    assert res.status_code == 200 and res.json()["credits"] == 3
    assert c.get("/auth/me").json()["credits"]["prices"]["dce_analysis"] == 3
    [line] = journal(db, "credit_price_changed")
    assert line.meta == {"action": "dce_analysis", "name": "Analyse du DCE", "from": 2, "to": 3}
    assert (
        client.put("/admin/credit-prices/dce_analysis", json={"credits": 1001}).status_code == 422
    )
    unknown = client.put("/admin/credit-prices/devis", json={"credits": 1})
    assert unknown.status_code == 404 and unknown.json()["error"]["message"] == "Action inconnue."


def test_company_session_refused(make_client: Factory, outbox: Outbox, db: Session) -> None:
    company = signed_in_client(make_client, outbox)
    some = plan_id(db, "Pilote")
    for method, path in [
        ("get", "/admin/plans"),
        ("post", "/admin/plans"),
        ("put", f"/admin/plans/{some}"),
        ("post", f"/admin/plans/{some}/archive"),
        ("post", f"/admin/plans/{some}/unarchive"),
        ("put", f"/admin/plans/{some}/default"),
        ("get", "/admin/credit-prices"),
        ("put", "/admin/credit-prices/dce_analysis"),
    ]:
        assert company.request(method, path, json={}).status_code == 401, path
