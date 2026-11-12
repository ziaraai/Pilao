"""Lot 4: a company's credits — plan at sign-up and creation, the balance it sees (spec §3.2)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import CreditEntry, CreditPrice, Organization, Plan, PlatformAdmin, User
from app.services import credits
from tests.api.helpers import signed_in_client, valid_siret
from tests.api.test_admin_accounts import admin, create
from tests.conftest import Outbox

REAL_CREDITS = True  # the plans' own credits, not the generous ones of the other tests
Factory = Callable[[], TestClient]
PRICES = {
    "dce_analysis": 2,
    "memoir_generation": 5,
    "chapter_regeneration": 1,
    "profile_prefill": 1,
}


def org_of(db: Session, email: str) -> Organization:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return db.get_one(Organization, user.org_id)


def plan_named(db: Session, name: str) -> Plan:
    plan = db.scalar(select(Plan).where(Plan.name == name))
    assert plan is not None
    return plan


def test_signup_gets_discovery_and_welcome(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    assert c.get("/auth/me").json()["credits"] == {"total": 7, "reference": 7, "prices": PRICES}
    org = org_of(db, "user1@example.fr")
    assert org.plan_id == plan_named(db, "Découverte").id
    [welcome] = db.scalars(select(CreditEntry).where(CreditEntry.org_id == org.id)).all()
    assert (welcome.kind, welcome.monthly, welcome.extra) == ("welcome", 0, 7)


def test_admin_created_company_gets_chosen_plan(make_client: Factory, db: Session) -> None:
    client, _, _ = admin(make_client, db)
    pilote = plan_named(db, "Pilote")
    chosen = create(client, plan_id=str(pilote.id)).json()["id"]
    org = db.get_one(Organization, chosen)
    assert org.plan_id == pilote.id
    assert credits.org_balance(db, org).total == 100
    assert db.scalar(select(CreditEntry).where(CreditEntry.org_id == org.id)) is None

    other = create(client, siret=valid_siret("7712345678901"), contact_email="b@example.fr").json()[
        "id"
    ]
    org2 = db.get_one(Organization, other)
    assert org2.plan_id == plan_named(db, "Découverte").id
    assert credits.org_balance(db, org2).total == 7


def test_credits_page(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    body = c.get("/credits").json()
    assert body["plan"] == {
        "name": "Découverte",
        "description": "Pour découvrir Pilao : de quoi répondre à un appel d'offres.",
        "modules": ["veille", "reponse"],
    }
    assert (body["monthly_allowance"], body["monthly_left"], body["extra"], body["total"]) == (
        0,
        0,
        7,
        7,
    )
    assert body["renews_on"]
    assert [(p["action"], p["name"], p["credits"]) for p in body["prices"]] == [
        ("dce_analysis", "Analyse du DCE", 2),
        ("memoir_generation", "Rédaction du mémoire", 5),
        ("chapter_regeneration", "Régénérer un chapitre", 1),
        ("profile_prefill", "Pré-remplir le profil depuis vos documents", 1),
    ]
    [line] = body["history"]
    assert (line["kind"], line["credits"], line["action_name"]) == ("welcome", 7, None)


def test_no_euro_on_the_client_side(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    for path in ("/auth/me", "/credits", "/dashboard"):
        text = c.get(path).text
        assert "€" not in text and "cost" not in text and "price_note" not in text, path


def test_isolation(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    neighbour = signed_in_client(make_client, outbox, 2)
    org = org_of(db, "user1@example.fr")
    admin(make_client, db)
    boss = db.scalar(select(PlatformAdmin))
    assert boss is not None
    credits.grant(db, org, 20, "Geste", boss)
    db.commit()

    body = neighbour.get("/credits").json()
    assert body["total"] == 7 and len(body["history"]) == 1


def test_charge_refused_message(
    make_client: Factory, outbox: Outbox, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    signed_in_client(make_client, outbox)
    org = org_of(db, "user1@example.fr")
    db.add(CreditPrice(action="memoir_generation", credits=10))
    db.commit()
    with pytest.raises(ApiError) as refused:
        credits.charge(db, org, "memoir_generation", user_id=None)
    assert (refused.value.status, refused.value.code) == (402, "credits_exhausted")
    assert refused.value.message == "Il faut 10 crédits, il vous en reste 7. Contactez Pilao."

    monkeypatch.setattr(get_settings(), "support_email", "aide@pilao.test")
    with pytest.raises(ApiError) as refused:
        credits.charge(db, org, "memoir_generation", user_id=None)
    assert refused.value.message.endswith("Contactez Pilao : aide@pilao.test.")

    db.get_one(CreditPrice, "memoir_generation").credits = 7
    assert credits.charge(db, org, "memoir_generation", user_id=None) is not None
    db.commit()
    with pytest.raises(ApiError) as refused:
        credits.charge(db, org, "chapter_regeneration", user_id=None)
    assert refused.value.message.startswith("Il faut 1 crédit, il vous en reste 0.")


def test_no_balance_without_a_paid_module(
    make_client: Callable[[], TestClient], outbox: Outbox, db: Session
) -> None:
    """« Veille » alone has no paid action: no balance, so no red banner at 0 (review I6)."""
    from tests.api.test_modules import set_modules

    c = signed_in_client(make_client, outbox)
    assert c.get("/auth/me").json()["credits"]["total"] == 7
    set_modules(db, "user1@example.fr", ["veille"])
    assert c.get("/auth/me").json()["credits"] is None
