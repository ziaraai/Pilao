from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.models import AuthToken
from tests.api.helpers import PASSWORD, register_payload, signed_in_client
from tests.conftest import Outbox

Factory = Callable[[], TestClient]


def test_register_creates_unverified_account_and_sends_email(
    make_client: Factory, outbox: Outbox
) -> None:
    c = make_client()
    res = c.post("/auth/register", json=register_payload())
    assert res.status_code == 201
    assert len(outbox.sent) == 1 and outbox.sent[0].to == "user1@example.fr"
    res = c.post("/auth/login", json={"email": "user1@example.fr", "password": PASSWORD})
    assert res.status_code == 403 and res.json()["error"]["code"] == "email_not_verified"


def test_register_validation(make_client: Factory) -> None:
    c = make_client()
    assert (
        c.post("/auth/register", json={**register_payload(), "password": "short"}).status_code
        == 422
    )
    assert (
        c.post("/auth/register", json={**register_payload(), "siret": "12345678901234"}).status_code
        == 422
    )
    assert c.post("/auth/register", json={**register_payload(), "email": "nope"}).status_code == 422


def test_register_rejects_duplicate_siret_and_email(make_client: Factory) -> None:
    c = make_client()
    assert c.post("/auth/register", json=register_payload(1)).status_code == 201
    same_siret = {**register_payload(2), "siret": register_payload(1)["siret"]}
    assert c.post("/auth/register", json=same_siret).json()["error"]["code"] == "siret_taken"
    same_email = {**register_payload(2), "email": "USER1@example.fr"}
    assert c.post("/auth/register", json=same_email).json()["error"]["code"] == "email_taken"


def test_full_flow_login_me_logout(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    cookie = c.cookies.get("pilao_session")
    assert cookie
    me = c.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "org_admin" and me.json()["org"]["name"] == "Entreprise 1"
    assert c.post("/auth/logout").status_code == 200
    c.cookies.set("pilao_session", cookie)  # the old cookie must be dead server-side
    assert c.get("/auth/me").status_code == 401


def test_session_cookie_is_httponly(make_client: Factory, outbox: Outbox) -> None:
    c = make_client()
    c.post("/auth/register", json=register_payload())
    c.post("/auth/verify-email", json={"token": outbox.last_token()})
    res = c.post("/auth/login", json={"email": "user1@example.fr", "password": PASSWORD})
    header = res.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=lax" in header


def test_verification_token_is_single_use_and_expires(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    c = make_client()
    c.post("/auth/register", json=register_payload())
    token = outbox.last_token()
    assert c.post("/auth/verify-email", json={"token": token}).status_code == 200
    assert c.post("/auth/verify-email", json={"token": token}).status_code == 400

    c.post("/auth/register", json=register_payload(2))
    token2 = outbox.last_token()
    db.execute(update(AuthToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    assert c.post("/auth/verify-email", json={"token": token2}).status_code == 400
    assert c.post("/auth/verify-email", json={"token": "x" * 40}).status_code == 400


def test_resend_verification_is_silent_for_unknown_email(
    make_client: Factory, outbox: Outbox
) -> None:
    c = make_client()
    assert (
        c.post("/auth/resend-verification", json={"email": "ghost@example.fr"}).status_code == 200
    )
    assert outbox.sent == []
    c.post("/auth/register", json=register_payload())
    c.post("/auth/resend-verification", json={"email": "user1@example.fr"})
    assert len(outbox.sent) == 2


def test_wrong_password_and_unknown_email_look_identical(
    make_client: Factory, outbox: Outbox
) -> None:
    c = signed_in_client(make_client, outbox)
    a = c.post("/auth/login", json={"email": "user1@example.fr", "password": "wrong-password-1"})
    b = c.post("/auth/login", json={"email": "ghost@example.fr", "password": "wrong-password-1"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


def test_login_is_throttled_after_repeated_failures(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    for _ in range(5):
        assert (
            c.post(
                "/auth/login", json={"email": "user1@example.fr", "password": "bad-password-1"}
            ).status_code
            == 401
        )
    res = c.post("/auth/login", json={"email": "user1@example.fr", "password": PASSWORD})
    assert res.status_code == 429  # even the right password is refused while throttled


def test_csrf_rejects_missing_or_foreign_origin(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    assert c.post("/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    c.headers.pop("Origin")
    assert c.post("/auth/logout").status_code == 403
    assert c.get("/auth/me").status_code == 200  # safe methods are fine
