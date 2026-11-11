"""Administration, lot 2: the minor points left by the final review, now fixed."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.email import Email
from app.core.errors import ApiError
from app.db.models import AuthToken, Organization, PlatformAuditLog, User
from tests.api.admin_helpers import code
from tests.api.helpers import signed_in_client
from tests.api.test_admin_accounts import admin, create, org_id_of
from tests.conftest import FakeQueue, Outbox

Factory = Callable[[], TestClient]


def mail_down(outbox: Outbox, monkeypatch: pytest.MonkeyPatch) -> None:
    def down(message: Email) -> None:
        raise ApiError(503, "email_unavailable", "L'e-mail n'a pas pu être envoyé : réessayez.")

    monkeypatch.setattr(outbox, "send", down)


def actions(db: Session) -> list[str]:
    return [a for a in db.scalars(select(PlatformAuditLog.action))]


def test_create_when_mail_is_down(
    make_client: Factory, outbox: Outbox, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, _ = admin(make_client, db)
    mail_down(outbox, monkeypatch)

    res = create(client)
    assert res.status_code == 201, res.text
    assert res.json()["email_sent"] is False  # created: the invitation is resent from its page
    assert db.get(Organization, res.json()["id"]) is not None
    assert "organization_created" in actions(db)


def test_invite_when_mail_is_down(
    make_client: Factory, outbox: Outbox, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    signed_in_client(make_client, outbox)
    org = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)
    mail_down(outbox, monkeypatch)

    res = client.post(f"/admin/organizations/{org}/users", json={"email": "col@example.fr"})
    assert res.status_code == 201, res.text
    assert res.json()["email_sent"] is False
    assert "user_invited" in actions(db)


def test_invitation_date_is_the_latest(make_client: Factory, outbox: Outbox, db: Session) -> None:
    c = signed_in_client(make_client, outbox)
    assert c.post("/organization/members", json={"email": "col@example.fr"}).status_code == 201
    org = org_id_of(db, "user1@example.fr")
    long_ago = datetime.now(UTC) - timedelta(days=3)
    db.execute(update(AuthToken).values(created_at=long_ago))
    db.execute(update(User).where(User.email == "col@example.fr").values(created_at=long_ago))
    db.commit()
    client, _, _ = admin(make_client, db)
    col = db.scalar(select(User.id).where(User.email == "col@example.fr"))
    assert client.post(f"/admin/organizations/{org}/users/{col}/invitation").status_code == 204

    users = client.get(f"/admin/organizations/{org}").json()["users"]
    [invited] = [u for u in users if u["email"] == "col@example.fr"]
    assert datetime.fromisoformat(invited["invited_at"]) > datetime.now(UTC) - timedelta(hours=1)


def test_list_shows_suspension_date_and_reason(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    signed_in_client(make_client, outbox)
    org = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)
    client.post(f"/admin/organizations/{org}/suspend", json={"reason": "Impayé"})

    [row] = client.get("/admin/organizations").json()
    assert row["suspension_reason"] == "Impayé" and row["suspended_at"] is not None


def test_resend_cap_message(make_client: Factory, outbox: Outbox, db: Session) -> None:
    c = signed_in_client(make_client, outbox)
    assert c.post("/organization/members", json={"email": "col@example.fr"}).status_code == 201
    org = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)
    col = db.scalar(select(User.id).where(User.email == "col@example.fr"))

    answers = [client.post(f"/admin/organizations/{org}/users/{col}/invitation") for _ in range(5)]
    assert answers[-1].status_code == 429
    assert answers[-1].json()["error"]["message"] == "Envoi déjà fait : réessayez plus tard."


def test_cancel_by_pilao_changes_the_reason(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    signed_in_client(make_client, outbox)
    org = org_id_of(db, "user1@example.fr")
    client, secret, _ = admin(make_client, db)
    client.post(
        f"/admin/organizations/{org}/deletion",
        json={"confirmation": "Entreprise 1", "code": code(secret)},
    )
    assert client.delete(f"/admin/organizations/{org}/deletion").status_code == 204

    db.expire_all()
    reason = db.get_one(Organization, org).suspension_reason
    assert reason == "Suppression annulée : réactivez l'entreprise pour lui rendre l'accès."


def test_reactivate_when_queue_is_down(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signed_in_client(make_client, outbox)
    org = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)
    client.post(f"/admin/organizations/{org}/suspend", json={"reason": "x"})

    def down(org_id: object) -> None:
        raise RuntimeError("redis down")

    monkeypatch.setattr(queue, "enqueue_rematch_org", down)
    assert client.post(f"/admin/organizations/{org}/reactivate").status_code == 204
    db.expire_all()
    assert db.get_one(Organization, org).suspended_at is None


def test_forgot_when_mail_is_down_same_answer(
    make_client: Factory, outbox: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    signed_in_client(make_client, outbox)
    mail_down(outbox, monkeypatch)

    known = make_client().post("/auth/password/forgot", json={"email": "user1@example.fr"})
    unknown = make_client().post("/auth/password/forgot", json={"email": "x@example.fr"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


def test_reset_closes_the_other_links(make_client: Factory, outbox: Outbox) -> None:
    signed_in_client(make_client, outbox)
    client = make_client()
    client.post("/auth/password/forgot", json={"email": "user1@example.fr"})
    first = outbox.last_token()
    client.post("/auth/password/forgot", json={"email": "user1@example.fr"})
    second = outbox.last_token()

    new = "un-tout-nouveau-mot-de-passe"
    assert (
        client.post("/auth/password/reset", json={"token": first, "password": new}).status_code
        == 200
    )
    late = client.post("/auth/password/reset/lookup", json={"token": second})
    assert late.status_code == 410  # a link sent before the change no longer works
