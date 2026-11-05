"""Colleagues of an organization (US-1.5): invitation, roles, removal."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.legal import TERMS_VERSION
from app.db.models import AuthToken, Bid, User
from tests.api.helpers import PASSWORD, signed_in_client
from tests.conftest import Outbox

Factory = Callable[[], TestClient]
COLLEAGUE = "secretaire@example.fr"


def invite(c: TestClient, email: str = COLLEAGUE, role: str = "org_member") -> dict:  # type: ignore[type-arg]
    res = c.post(
        "/organization/members", json={"email": email, "role": role, "full_name": "Sophie"}
    )
    assert res.status_code == 201, res.text
    return res.json()  # type: ignore[no-any-return]


def join(make_client: Factory, outbox: Outbox, name: str = "Sophie Martin") -> TestClient:
    colleague = make_client()
    body = {
        "token": outbox.last_token(),
        "full_name": name,
        "password": PASSWORD,
        "accept_terms": True,
    }
    res = colleague.post("/auth/invitations/accept", json=body)
    assert res.status_code == 200, res.text
    return colleague


def test_an_admin_invites_a_colleague_who_joins_with_the_link(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    admin = signed_in_client(make_client, outbox, 1)
    member = invite(admin)
    assert (member["email"], member["role"], member["status"]) == (
        COLLEAGUE,
        "org_member",
        "invited",
    )
    [mail] = outbox.sent[-1:]
    assert mail.to == COLLEAGUE and mail.subject == "User 1 vous invite sur Pilao (Entreprise 1)"
    assert "/invitation?token=" in mail.body and "valable 7 jours" in mail.body
    token = outbox.last_token()

    anon = make_client()  # no password yet: no way in but the link
    login = {"email": COLLEAGUE, "password": PASSWORD}
    assert anon.post("/auth/login", json=login).status_code == 401
    sent = len(outbox.sent)
    anon.post("/auth/resend-verification", json={"email": COLLEAGUE})
    assert len(outbox.sent) == sent  # a confirmation link would leave the account without password

    found = anon.post("/auth/invitations/lookup", json={"token": token}).json()
    assert found == {
        "email": COLLEAGUE,
        "full_name": "Sophie",
        "org_name": "Entreprise 1",
        "role": "org_member",
    }
    body = {"token": token, "full_name": "Sophie Martin", "password": PASSWORD}
    refused = anon.post("/auth/invitations/accept", json={**body, "accept_terms": False})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "terms_required"
    short = anon.post(
        "/auth/invitations/accept", json={**body, "password": "court", "accept_terms": True}
    )
    assert short.status_code == 422

    colleague = join(make_client, outbox)  # the same link, now accepted: a session is open
    me = colleague.get("/auth/me").json()
    assert (me["email"], me["role"], me["org"]["name"]) == (COLLEAGUE, "org_member", "Entreprise 1")
    user = db.scalars(select(User).where(User.email == COLLEAGUE)).one()
    assert user.email_verified_at is not None and user.terms_version == TERMS_VERSION
    again = make_client().post("/auth/invitations/accept", json={**body, "accept_terms": True})
    assert again.status_code == 410 and again.json()["error"]["code"] == "invitation_invalid"
    assert make_client().post("/auth/invitations/lookup", json={"token": token}).status_code == 410
    assert make_client().post("/auth/login", json=login).status_code == 200

    # one company, two people: the colleague works on the same bids
    bid = admin.post("/bids", json={"title": "Médiathèque"}).json()
    assert [b["id"] for b in colleague.get("/bids").json()] == [bid["id"]]
    listed = {m["email"]: m for m in colleague.get("/organization/members").json()}
    assert listed[COLLEAGUE]["is_me"] and not listed["user1@example.fr"]["is_me"]
    assert {m["status"] for m in listed.values()} == {"active"}
    # a colleague manages nobody
    assert (
        colleague.post("/organization/members", json={"email": "x@example.fr"}).status_code == 403
    )
    assert colleague.delete(f"/organization/members/{me['id']}").status_code == 403


def test_the_company_always_keeps_an_administrator(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    admin = signed_in_client(make_client, outbox, 1)
    other = signed_in_client(make_client, outbox, 2)  # another company, with its own admin
    me = admin.get("/auth/me").json()
    invite(admin, role="org_admin")
    second = join(make_client, outbox)
    second_id = second.get("/auth/me").json()["id"]

    assert (
        admin.patch(f"/organization/members/{second_id}", json={"role": "org_member"}).json()[
            "role"
        ]
        == "org_member"
    )
    last = admin.patch(f"/organization/members/{me['id']}", json={"role": "org_member"})
    assert (
        last.status_code == 409 and last.json()["error"]["code"] == "last_admin"
    )  # company 2's admin does not count
    self_removal = admin.delete(f"/organization/members/{me['id']}")
    assert (
        self_removal.status_code == 409 and self_removal.json()["error"]["code"] == "self_removal"
    )

    bid = second.post("/bids", json={"title": "Écoles"}).json()  # work done by the colleague
    assert (
        other.patch(f"/organization/members/{second_id}", json={"role": "org_admin"}).status_code
        == 404
    )
    assert other.delete(f"/organization/members/{second_id}").status_code == 404
    assert [m["email"] for m in other.get("/organization/members").json()] == ["user2@example.fr"]

    assert admin.delete(f"/organization/members/{second_id}").status_code == 204
    assert second.get("/auth/me").status_code == 401  # sessions went with the account
    assert db.scalar(select(User).where(User.email == COLLEAGUE)) is None
    kept = db.get_one(Bid, bid["id"])
    db.refresh(kept)
    assert kept.owner_user_id is None and kept.title == "Écoles"  # the work stays
    assert [m["email"] for m in admin.get("/organization/members").json()] == ["user1@example.fr"]


def test_invitation_rules(
    make_client: Factory, outbox: Outbox, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = signed_in_client(make_client, outbox, 1)
    signed_in_client(make_client, outbox, 2)
    for taken in ("user2@example.fr", "USER1@example.fr"):  # any account of Pilao
        res = admin.post("/organization/members", json={"email": taken})
        assert res.status_code == 409 and res.json()["error"]["code"] == "email_taken"
    member = invite(admin)
    assert admin.post("/organization/members", json={"email": COLLEAGUE.upper()}).status_code == 409

    db.execute(
        update(AuthToken)
        .where(AuthToken.kind == "invitation")
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    db.commit()
    expired = make_client().post("/auth/invitations/lookup", json={"token": outbox.last_token()})
    assert expired.status_code == 410
    [row] = [m for m in admin.get("/organization/members").json() if m["email"] == COLLEAGUE]
    assert row["status"] == "invitation_expired"
    assert admin.post(f"/organization/members/{member['id']}/resend").status_code == 204
    assert [
        m["status"] for m in admin.get("/organization/members").json() if m["email"] == COLLEAGUE
    ] == ["invited"]
    for _ in range(get_settings().email_verify_max_per_hour - 2):
        admin.post(f"/organization/members/{member['id']}/resend")
    capped = admin.post(f"/organization/members/{member['id']}/resend")
    assert capped.status_code == 429  # nobody is mail-bombed through an invitation
    join(make_client, outbox)  # the latest link works
    active = admin.post(f"/organization/members/{member['id']}/resend")
    assert active.status_code == 409 and active.json()["error"]["code"] == "already_active"

    monkeypatch.setattr(get_settings(), "max_users_per_org", 2)
    full = admin.post("/organization/members", json={"email": "trois@example.fr"})
    assert full.status_code == 409 and full.json()["error"]["code"] == "too_many_users"


def test_members_need_an_account(make_client: Factory) -> None:
    anon = make_client()
    assert anon.get("/organization/members").status_code == 401
    assert anon.post("/organization/members", json={"email": "x@example.fr"}).status_code == 401
    bad = anon.post("/auth/invitations/lookup", json={"token": "nimportequoi"})
    assert bad.status_code == 410
