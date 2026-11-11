"""Administration, lot 2: create, suspend, reactivate and delete a company (spec §2.1 to §2.3)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DataRequest, Organization, PlatformAuditLog, PurgeLog, User
from app.services.admin.access import grant_access
from tests.api.admin_helpers import ADMIN_EMAIL, ADMIN_PASSWORD, code
from tests.api.helpers import PASSWORD, register_payload, signed_in_client, valid_siret
from tests.conftest import FakeQueue, Outbox

Factory = Callable[[], TestClient]
NEW_SIRET = valid_siret("9876543210")


def admin(make_client: Factory, db: Session) -> tuple[TestClient, str, list[str]]:
    """A signed-in super admin whose last used step is the previous one: the current and the
    next step are both left for the codes asked again, plus the 8 recovery codes."""
    client = make_client()
    token = grant_access(db, ADMIN_EMAIL, "Admin")
    chosen = client.post(
        "/admin/auth/setup/password", json={"token": token, "password": ADMIN_PASSWORD}
    )
    assert chosen.status_code == 200, chosen.text
    secret = chosen.json()["secret"]
    # Computed right before the confirmation: the password hashing above takes time.
    previous = code(secret, when=datetime.now(UTC) - timedelta(seconds=30))
    done = client.post("/admin/auth/setup/confirm", json={"token": token, "code": previous})
    assert done.status_code == 200, done.text
    return client, secret, done.json()["recovery_codes"]


def org_id_of(db: Session, email: str) -> str:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return str(user.org_id)


def journal(db: Session, action: str) -> list[PlatformAuditLog]:
    return list(db.scalars(select(PlatformAuditLog).where(PlatformAuditLog.action == action)))


def create(client: TestClient, **kw: str):  # type: ignore[no-untyped-def]
    body = {
        "siret": NEW_SIRET,
        "name": "Propreté Test",
        "contact_name": "Jean Patron",
        "contact_email": "patron@example.fr",
        **kw,
    }
    return client.post("/admin/organizations", json=body)


def test_create_organization_and_accept(make_client: Factory, outbox: Outbox, db: Session) -> None:
    client, _, _ = admin(make_client, db)

    res = create(client)
    assert res.status_code == 201, res.text
    org_id = res.json()["id"]
    mail = outbox.sent[-1]
    assert (mail.to, mail.subject) == (
        "patron@example.fr",
        "Pilao a ouvert l'espace de Propreté Test",
    )
    assert mail.body.startswith("Bonjour Jean Patron,")

    patron = make_client()
    accepted = patron.post(
        "/auth/invitations/accept",
        json={
            "token": outbox.last_token(),
            "full_name": "Jean Patron",
            "password": PASSWORD,
            "accept_terms": True,
        },
    )
    assert accepted.status_code == 200, accepted.text
    me = patron.get("/auth/me").json()
    assert me["role"] == "org_admin" and me["org"]["name"] == "Propreté Test"
    [entry] = journal(db, "organization_created")
    assert str(entry.org_id) == org_id and entry.meta["email"] == "patron@example.fr"


def test_create_refusals(make_client: Factory, outbox: Outbox, db: Session) -> None:
    company = signed_in_client(make_client, outbox)
    client, _, _ = admin(make_client, db)

    taken = create(client, siret=str(register_payload(1)["siret"]))
    assert taken.status_code == 409
    assert taken.json()["error"]["message"] == "Ce SIRET a déjà un compte : Entreprise 1."
    email = create(client, contact_email="user1@example.fr")
    assert email.status_code == 409 and email.json()["error"]["code"] == "email_taken"
    assert create(client, siret="12345678901234").status_code == 422
    assert create(company).status_code == 401  # a company session is not an admin session
    assert db.scalar(select(Organization).where(Organization.siret == NEW_SIRET)) is None


def test_suspend_and_reactivate(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    company = signed_in_client(make_client, outbox)
    org_id = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    assert (
        client.post(f"/admin/organizations/{org_id}/suspend", json={"reason": ""}).status_code
        == 422
    )
    res = client.post(f"/admin/organizations/{org_id}/suspend", json={"reason": "Impayé"})
    assert res.status_code == 204, res.text
    assert company.get("/auth/me").status_code == 403
    login = make_client().post(
        "/auth/login", json={"email": "user1@example.fr", "password": PASSWORD}
    )
    assert login.status_code == 403

    assert client.post(f"/admin/organizations/{org_id}/reactivate").status_code == 204
    login = make_client().post(
        "/auth/login", json={"email": "user1@example.fr", "password": PASSWORD}
    )
    assert login.status_code == 200
    assert [str(o) for o in queue.pending_rematch] == [org_id]  # the watch catches up
    [suspended] = journal(db, "organization_suspended")
    assert suspended.meta["reason"] == "Impayé"
    assert len(journal(db, "organization_reactivated")) == 1


def test_delete_never_used_is_immediate(make_client: Factory, outbox: Outbox, db: Session) -> None:
    client, secret, _ = admin(make_client, db)
    org_id = create(client).json()["id"]
    sent = len(outbox.sent)

    preview = client.get(f"/admin/organizations/{org_id}/deletion")
    assert preview.json() == {"mode": "immediate", "due_at": None, "pending": False, "by": None}
    res = client.post(
        f"/admin/organizations/{org_id}/deletion",
        json={"confirmation": "propreté test", "code": code(secret)},
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"mode": "immediate", "due_at": None}
    db.expire_all()
    assert db.get(Organization, org_id) is None
    assert db.scalar(select(PurgeLog).where(PurgeLog.org_id == org_id)) is not None
    assert len(outbox.sent) == sent  # nobody to tell
    [entry] = journal(db, "organization_deleted")
    assert entry.meta["mode"] == "immediate"


def test_delete_used_is_scheduled_and_cancellable(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    company = signed_in_client(make_client, outbox)
    org_id = org_id_of(db, "user1@example.fr")
    client, secret, _ = admin(make_client, db)

    assert client.get(f"/admin/organizations/{org_id}/deletion").json()["mode"] == "scheduled"
    res = client.post(
        f"/admin/organizations/{org_id}/deletion",
        json={"confirmation": "Entreprise 1", "code": code(secret)},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "scheduled"
    due = datetime.fromisoformat(body["due_at"])
    assert timedelta(days=29) < due - datetime.now(UTC) <= timedelta(days=30)
    db.expire_all()
    org = db.get_one(Organization, org_id)
    assert org.suspended_at is not None
    assert org.suspension_reason == "Suppression programmée par Pilao"
    assert company.get("/auth/me").status_code == 403
    assert outbox.sent[-1].subject.startswith("Suppression des données de Entreprise 1 programmée")
    preview = client.get(f"/admin/organizations/{org_id}/deletion").json()
    assert preview["pending"] is True and preview["by"] == "pilao"

    assert client.delete(f"/admin/organizations/{org_id}/deletion").status_code == 204
    db.expire_all()
    req = db.scalar(select(DataRequest).where(DataRequest.kind == "deletion"))
    assert req is not None and req.status == "cancelled"
    assert db.get_one(Organization, org_id).suspended_at is not None  # « Réactiver » is explicit
    assert len(journal(db, "deletion_cancelled")) == 1


def test_cancel_client_request_keeps_access(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    company = signed_in_client(make_client, outbox)
    asked = company.post("/organization/deletion", json={"confirmation": "Entreprise 1"})
    assert asked.status_code == 202, asked.text
    org_id = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    preview = client.get(f"/admin/organizations/{org_id}/deletion").json()
    assert preview["pending"] is True and preview["by"] == "client"
    assert client.delete(f"/admin/organizations/{org_id}/deletion").status_code == 204
    assert company.get("/auth/me").status_code == 200  # never suspended: still in


def test_race_first_login_turns_scheduled(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    client, secret, _ = admin(make_client, db)
    org_id = create(client).json()["id"]
    assert client.get(f"/admin/organizations/{org_id}/deletion").json()["mode"] == "immediate"
    patron = db.scalar(select(User).where(User.email == "patron@example.fr"))
    assert patron is not None
    patron.last_login_at = datetime.now(UTC)  # signed in between the preview and the click
    db.commit()

    res = client.post(
        f"/admin/organizations/{org_id}/deletion",
        json={"confirmation": "Propreté Test", "code": code(secret)},
    )
    assert res.status_code == 200 and res.json()["mode"] == "scheduled"
    db.expire_all()
    assert db.get(Organization, org_id) is not None


def test_codes_asked_again(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    used = org_id_of(db, "user1@example.fr")
    client, secret, recovery = admin(make_client, db)
    fresh = create(client).json()["id"]

    wrong_name = client.post(
        f"/admin/organizations/{used}/deletion", json={"confirmation": "X", "code": code(secret)}
    )
    assert wrong_name.status_code == 422  # checked first: the code is not spent
    wrong = client.post(
        f"/admin/organizations/{used}/deletion",
        json={"confirmation": "Entreprise 1", "code": "000000"},
    )
    assert wrong.status_code == 400 and wrong.json()["error"]["message"] == "Code incorrect."
    right = code(secret)
    ok = client.post(
        f"/admin/organizations/{fresh}/deletion",
        json={"confirmation": "Propreté Test", "code": right},
    )
    assert ok.status_code == 200, ok.text
    replay = client.post(
        f"/admin/organizations/{used}/deletion",
        json={"confirmation": "Entreprise 1", "code": right},
    )
    assert replay.status_code == 400
    typed = recovery[0].replace("-", "").upper()
    res = client.post(
        f"/admin/organizations/{used}/deletion",
        json={"confirmation": "Entreprise 1", "code": typed},
    )
    assert res.status_code == 200, res.text
    assert len(journal(db, "step_up_failed")) == 2


def test_five_wrong_codes_close_the_session(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    signed_in_client(make_client, outbox)
    org_id = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    answers = [
        client.post(
            f"/admin/organizations/{org_id}/deletion",
            json={"confirmation": "Entreprise 1", "code": "000000"},
        ).status_code
        for _ in range(5)
    ]
    assert answers == [400, 400, 400, 400, 401]
    assert client.get("/admin/auth/me").status_code == 401
    db.expire_all()
    assert db.scalar(select(DataRequest)) is None


def test_other_org_untouched(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    other = signed_in_client(make_client, outbox, 2)
    org_id = org_id_of(db, "user1@example.fr")
    client, secret, _ = admin(make_client, db)

    assert (
        client.post(f"/admin/organizations/{org_id}/suspend", json={"reason": "x"}).status_code
        == 204
    )
    res = client.post(
        f"/admin/organizations/{org_id}/deletion",
        json={"confirmation": "Entreprise 1", "code": code(secret)},
    )
    assert res.status_code == 200
    assert other.get("/auth/me").status_code == 200
    db.expire_all()
    second = db.get_one(Organization, org_id_of(db, "user2@example.fr"))
    assert second.suspended_at is None
    assert (
        client.post(
            "/admin/organizations/00000000-0000-0000-0000-000000000000/suspend",
            json={"reason": "x"},
        ).status_code
        == 404
    )
