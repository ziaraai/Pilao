"""« Mot de passe oublié ? » (US-1.6, spec §2.5): a one-hour, single-use link."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import AuthToken, User
from tests.api.helpers import PASSWORD, register_payload, signed_in_client
from tests.api.test_suspension import suspend
from tests.conftest import Outbox

Factory = Callable[[], TestClient]
ANSWER = "Si un compte existe pour cette adresse, un e-mail vient de partir. Le lien est valable 1 heure."
NEW_PASSWORD = "un-tout-nouveau-mot-de-passe"
SUBJECT = "Choisir un nouveau mot de passe Pilao"


def forgot(client: TestClient, email: str):  # type: ignore[no-untyped-def]
    return client.post("/auth/password/forgot", json={"email": email})


def reset_tokens(db: Session) -> list[AuthToken]:
    return list(db.scalars(select(AuthToken).where(AuthToken.kind == "password_reset")))


def test_same_answer_for_everyone(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    signed_in_client(make_client, outbox, 2)
    suspend(db, "user2@example.fr")
    client = make_client()
    before = len(outbox.sent)

    answers = [
        forgot(client, email)
        for email in ("inconnu@example.fr", "user1@example.fr", "user2@example.fr")
    ]
    assert {a.status_code for a in answers} == {202}
    assert {a.json()["message"] for a in answers} == {ANSWER}
    sent = outbox.sent[before:]
    assert [(m.to, m.subject) for m in sent] == [("user1@example.fr", SUBJECT)]
    assert "/nouveau-mot-de-passe?token=" in sent[0].body
    assert "valable 1 heure" in sent[0].body
    assert "votre mot de passe ne change pas" in sent[0].body


def test_address_typed_differently(make_client: Factory, outbox: Outbox) -> None:
    signed_in_client(make_client, outbox)
    before = len(outbox.sent)

    assert forgot(make_client(), "  User1@Example.FR ").status_code == 202
    assert [m.to for m in outbox.sent[before:]] == ["user1@example.fr"]


def test_invited_account_gets_an_invitation(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    assert c.post("/organization/members", json={"email": "col@example.fr"}).status_code == 201
    before = len(outbox.sent)

    assert forgot(make_client(), "col@example.fr").status_code == 202
    [mail] = outbox.sent[before:]
    assert mail.subject == "Créez votre accès à Pilao (Entreprise 1)"
    assert "votre accès n'est pas encore créé" in mail.body and "/invitation?token=" in mail.body
    assert reset_tokens(db) == []


def test_reset_end_to_end(make_client: Factory, outbox: Outbox, db: Session) -> None:
    old_session = signed_in_client(make_client, outbox)
    client = make_client()
    forgot(client, "user1@example.fr")
    token = outbox.last_token()

    lookup = client.post("/auth/password/reset/lookup", json={"token": token})
    assert lookup.status_code == 200 and lookup.json() == {"email": "user1@example.fr"}
    done = client.post("/auth/password/reset", json={"token": token, "password": NEW_PASSWORD})
    assert done.status_code == 200, done.text
    assert done.json()["email"] == "user1@example.fr"
    assert client.get("/auth/me").status_code == 200  # signed in on the way out
    assert old_session.get("/auth/me").status_code == 401  # every other session closed
    login = make_client().post(
        "/auth/login", json={"email": "user1@example.fr", "password": PASSWORD}
    )
    assert login.status_code == 401
    login = make_client().post(
        "/auth/login", json={"email": "user1@example.fr", "password": NEW_PASSWORD}
    )
    assert login.status_code == 200


def test_reset_confirms_the_address(make_client: Factory, outbox: Outbox, db: Session) -> None:
    client = make_client()
    assert client.post("/auth/register", json=register_payload(3)).status_code == 201
    forgot(client, "user3@example.fr")
    token = outbox.last_token()

    done = client.post("/auth/password/reset", json={"token": token, "password": NEW_PASSWORD})
    assert done.status_code == 200, done.text
    user = db.scalar(select(User).where(User.email == "user3@example.fr"))
    assert user is not None and user.email_verified_at is not None


def test_link_single_use_and_expiry(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    client = make_client()
    forgot(client, "user1@example.fr")
    token = outbox.last_token()

    short = client.post("/auth/password/reset", json={"token": token, "password": "a" * 11})
    assert short.status_code == 422
    assert (
        client.post(
            "/auth/password/reset", json={"token": token, "password": NEW_PASSWORD}
        ).status_code
        == 200
    )
    again = client.post("/auth/password/reset", json={"token": token, "password": NEW_PASSWORD})
    assert again.status_code == 410
    assert again.json()["error"]["message"] == (
        "Ce lien n'est plus valable. Demandez-en un nouveau."
    )

    forgot(client, "user1@example.fr")
    late = outbox.last_token()
    db.execute(
        update(AuthToken)
        .where(AuthToken.kind == "password_reset", AuthToken.used_at.is_(None))
        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    db.commit()
    assert client.post("/auth/password/reset/lookup", json={"token": late}).status_code == 410


def test_cap_per_hour(make_client: Factory, outbox: Outbox) -> None:
    signed_in_client(make_client, outbox)
    client = make_client()
    before = len(outbox.sent)

    answers = [forgot(client, "user1@example.fr") for _ in range(6)]
    assert {a.status_code for a in answers} == {202}
    assert len(outbox.sent) - before == 5
