"""Administration, lot 2: helping a company's users (spec §2.4) and the account state shown."""

from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog, PlatformAuditLog, User
from tests.api.admin_helpers import code
from tests.api.helpers import register_payload, signed_in_client
from tests.api.test_admin_accounts import admin, create, org_id_of
from tests.conftest import Outbox

Factory = Callable[[], TestClient]


def user_id(db: Session, email: str) -> str:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return str(user.id)


def journal(db: Session, action: str) -> list[PlatformAuditLog]:
    return list(db.scalars(select(PlatformAuditLog).where(PlatformAuditLog.action == action)))


def test_invite_and_resend(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    org = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    res = client.post(
        f"/admin/organizations/{org}/users",
        json={"email": "col@example.fr", "full_name": "Col", "role": "org_member"},
    )
    assert res.status_code == 201, res.text
    assert outbox.sent[-1].subject == "L'équipe Pilao vous invite sur Pilao (Entreprise 1)"
    col = user_id(db, "col@example.fr")
    assert client.post(f"/admin/organizations/{org}/users/{col}/invitation").status_code == 204
    assert outbox.sent[-1].to == "col@example.fr"

    history = db.scalars(select(AuditLog).where(AuditLog.entity_id == col)).all()
    assert {a.action for a in history} == {"invite", "resend_invitation"}
    assert all(a.user_id is None and a.meta == {"by": "pilao"} for a in history)
    [invited] = journal(db, "user_invited")
    assert invited.meta["email"] == "col@example.fr" and str(invited.org_id) == org
    assert len(journal(db, "invitation_resent")) == 1


def test_verification_and_password_links(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    assert make_client().post("/auth/register", json=register_payload(3)).status_code == 201
    org1, org3 = org_id_of(db, "user1@example.fr"), org_id_of(db, "user3@example.fr")
    client, _, _ = admin(make_client, db)
    user1, user3 = user_id(db, "user1@example.fr"), user_id(db, "user3@example.fr")

    sent = client.post(f"/admin/organizations/{org3}/users/{user3}/verification")
    assert sent.status_code == 204
    assert outbox.sent[-1].subject == "Confirmez votre adresse e-mail — Pilao"
    done = client.post(f"/admin/organizations/{org1}/users/{user1}/verification")
    assert done.status_code == 409 and done.json()["error"]["code"] == "already_verified"

    link = client.post(f"/admin/organizations/{org1}/users/{user1}/password-reset")
    assert link.status_code == 204
    assert outbox.sent[-1].subject == "Choisir un nouveau mot de passe Pilao"
    invited = client.post(
        f"/admin/organizations/{org1}/users", json={"email": "col@example.fr"}
    ).json()["id"]
    no_password = client.post(f"/admin/organizations/{org1}/users/{invited}/password-reset")
    assert no_password.status_code == 409
    assert no_password.json()["error"]["message"] == ("Pas encore d'accès : renvoyez l'invitation.")
    answers = [
        client.post(f"/admin/organizations/{org1}/users/{user1}/password-reset").status_code
        for _ in range(5)
    ]
    assert answers == [204, 204, 204, 204, 429]  # 5 an hour, the first one included
    assert len(journal(db, "password_reset_sent")) == 5
    assert len(journal(db, "verification_resent")) == 1


def test_role_logout_remove(make_client: Factory, outbox: Outbox, db: Session) -> None:
    company = signed_in_client(make_client, outbox)
    assert (
        company.post("/organization/members", json={"email": "col@example.fr"}).status_code == 201
    )
    org = org_id_of(db, "user1@example.fr")
    client, secret, _ = admin(make_client, db)
    user1, col = user_id(db, "user1@example.fr"), user_id(db, "col@example.fr")
    base = f"/admin/organizations/{org}/users"

    assert client.patch(f"{base}/{col}", json={"role": "org_admin"}).status_code == 204
    assert client.patch(f"{base}/{user1}", json={"role": "org_member"}).status_code == 204
    assert client.post(f"{base}/{user1}/logout").status_code == 204
    assert company.get("/auth/me").status_code == 401

    last = client.post(f"{base}/{col}/remove", json={"code": code(secret)})
    assert last.status_code == 409 and last.json()["error"]["code"] == "last_admin"
    assert client.post(f"{base}/{user1}/remove", json={}).status_code == 422
    wrong = client.post(f"{base}/{user1}/remove", json={"code": "000000"})
    assert wrong.status_code == 400
    assert client.post(f"{base}/{user1}/remove", json={"code": code(secret, 1)}).status_code == 204
    assert db.scalar(select(User).where(User.email == "user1@example.fr")) is None
    assert {a.action for a in db.scalars(select(PlatformAuditLog))} >= {
        "role_changed",
        "user_logged_out",
        "user_removed",
        "step_up_failed",
    }


def test_suspended_company_sends_nothing(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    org = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)
    user1 = user_id(db, "user1@example.fr")
    assert (
        client.post(f"/admin/organizations/{org}/suspend", json={"reason": "x"}).status_code == 204
    )
    sent = len(outbox.sent)

    invite = client.post(f"/admin/organizations/{org}/users", json={"email": "col@example.fr"})
    assert invite.status_code == 409
    assert invite.json()["error"]["message"] == "Entreprise suspendue : réactivez-la d'abord."
    assert (
        client.post(f"/admin/organizations/{org}/users/{user1}/password-reset").status_code == 409
    )
    assert len(outbox.sent) == sent
    assert client.post(f"/admin/organizations/{org}/users/{user1}/logout").status_code == 204


def test_other_company_user_is_not_found(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    signed_in_client(make_client, outbox, 2)
    org1 = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)
    user2 = user_id(db, "user2@example.fr")

    for res in (
        client.post(f"/admin/organizations/{org1}/users/{user2}/logout"),
        client.patch(f"/admin/organizations/{org1}/users/{user2}", json={"role": "org_member"}),
        client.post(f"/admin/organizations/{org1}/users/{user2}/password-reset"),
    ):
        assert res.status_code == 404
    second = make_client().post(
        "/auth/login", json={"email": "user2@example.fr", "password": "correct-horse-battery"}
    )
    assert second.status_code == 200  # untouched


def test_detail_shows_account_state(make_client: Factory, outbox: Outbox, db: Session) -> None:
    company = signed_in_client(make_client, outbox)
    assert (
        company.post("/organization/members", json={"email": "col@example.fr"}).status_code == 201
    )
    org = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)
    created = create(client, name="Neuve", contact_email="n@example.fr")
    assert created.status_code == 201, created.text

    detail = client.get(f"/admin/organizations/{org}").json()
    assert detail["account"] == {
        "suspended_at": None,
        "suspension_reason": None,
        "deletion_due_at": None,
        "deletion_by": None,
    }
    users = {u["email"]: u for u in detail["users"]}
    assert users["user1@example.fr"]["status"] == "active"
    assert users["user1@example.fr"]["has_sessions"] is True
    assert users["col@example.fr"]["status"] == "invited"
    assert users["col@example.fr"]["invited_at"] is not None
    assert users["col@example.fr"]["id"] == user_id(db, "col@example.fr")

    client.post(f"/admin/organizations/{org}/suspend", json={"reason": "Impayé"})
    detail = client.get(f"/admin/organizations/{org}").json()
    assert detail["account"]["suspension_reason"] == "Impayé"
    rows = {r["name"]: r for r in client.get("/admin/organizations").json()}
    assert rows["Entreprise 1"]["suspended"] is True
    assert rows["Entreprise 1"]["siret"] == str(register_payload(1)["siret"])
    assert rows["Neuve"]["invitation_pending"] is True
    assert rows["Entreprise 1"]["invitation_pending"] is False
