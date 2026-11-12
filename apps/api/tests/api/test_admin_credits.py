"""Administration, lot 4: a company's plan and credits (spec §3.1)."""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CreditEntry, Organization, Plan
from app.domain.credits import paris_month
from tests.api.helpers import signed_in_client
from tests.api.test_admin_accounts import admin, journal, org_id_of
from tests.api.test_modules import set_modules
from tests.conftest import Outbox

REAL_CREDITS = True
Factory = Callable[[], TestClient]


def plan_id(db: Session, name: str) -> str:
    return str(db.scalars(select(Plan.id).where(Plan.name == name)).one())


def change(client: TestClient, org: str, plan: str):  # type: ignore[no-untyped-def]
    return client.put(f"/admin/organizations/{org}/plan", json={"plan_id": plan})


def test_change_of_plan(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    set_modules(db, "user1@example.fr", ["veille"])  # an exception
    org = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    res = change(client, org, plan_id(db, "Pilote"))
    assert res.status_code == 200, res.text
    b = res.json()
    assert b["plan"]["name"] == "Pilote"
    assert (b["monthly_allowance"], b["monthly_left"], b["extra"], b["total"]) == (100, 100, 7, 107)
    db.expire_all()
    assert db.get_one(Organization, uuid.UUID(org)).modules == ["veille", "reponse"]
    [line] = journal(db, "plan_changed")
    assert line.meta == {"from": "Découverte", "to": "Pilote"}

    archived = Plan(
        name="Ancienne", modules=["veille"], archived_at=db.scalar(select(Plan.created_at))
    )
    db.add(archived)
    db.commit()
    assert change(client, org, str(archived.id)).status_code == 409
    assert change(client, org, str(uuid.uuid4())).status_code == 404


def test_welcome_credits_are_never_given_twice(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    signed_in_client(make_client, outbox)  # « Découverte »: 7 offered
    org = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)
    change(client, org, plan_id(db, "Pilote"))
    back = change(client, org, plan_id(db, "Découverte")).json()
    assert back["total"] == 7
    db.expire_all()
    assert len(db.scalars(select(CreditEntry).where(CreditEntry.kind == "welcome")).all()) == 1


def test_top_up_and_history(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    org = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)
    url = f"/admin/organizations/{org}/credits"

    res = client.post(url, json={"amount": 20, "reason": " Geste commercial "})
    assert res.status_code == 200, res.text
    assert res.json()["total"] == 27
    first = res.json()["history"][0]
    assert (first["kind"], first["credits"], first["reason"], first["user_name"]) == (
        "grant",
        20,
        "Geste commercial",
        "Pilao",
    )
    [line] = journal(db, "credits_added")
    assert line.meta == {"amount": 20, "reason": "Geste commercial"}
    for bad in (
        {"amount": 0, "reason": "x"},
        {"amount": 100_001, "reason": "x"},
        {"amount": 5, "reason": ""},
        {"amount": 5, "reason": "   "},
    ):
        assert client.post(url, json=bad).status_code == 422, bad
    assert client.get(url).json()["total"] == 27


def test_list_page_and_watch(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    signed_in_client(make_client, outbox, 2)
    one, two = org_id_of(db, "user1@example.fr"), org_id_of(db, "user2@example.fr")
    db.add(
        CreditEntry(
            org_id=uuid.UUID(two),
            kind="charge",
            action="memoir_generation",
            extra=-7,
            month=paris_month(db.scalar(select(Plan.created_at))),  # type: ignore[arg-type]
        )
    )
    db.commit()
    set_modules(db, "user1@example.fr", ["veille"])
    client, _, _ = admin(make_client, db)

    rows = {r["id"]: r for r in client.get("/admin/organizations").json()}
    assert rows[one]["plan"]["name"] == "Découverte" and rows[one]["credits_total"] == 7
    assert rows[two]["credits_total"] == 0
    detail = client.get(f"/admin/organizations/{one}").json()
    assert detail["plan"]["name"] == "Découverte" and detail["credits_total"] == 7
    assert detail["modules_off_plan"] == {"added": [], "removed": ["reponse"]}
    watch = client.get("/admin/overview").json()["watch"]
    out = [w for w in watch if w["kind"] == "credits"]
    assert [(w["title"], w["level"], w["org_id"]) for w in out] == [
        ("Entreprise 2 n'a plus de crédits", "amber", two)
    ]


def test_company_session_refused(make_client: Factory, outbox: Outbox, db: Session) -> None:
    company = signed_in_client(make_client, outbox)
    org = org_id_of(db, "user1@example.fr")
    for method, path in [
        ("put", f"/admin/organizations/{org}/plan"),
        ("post", f"/admin/organizations/{org}/credits"),
        ("get", f"/admin/organizations/{org}/credits"),
    ]:
        assert company.request(method, path, json={}).status_code == 401, path
