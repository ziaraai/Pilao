"""Super admin access: activation link, password + authenticator code, sessions (US-6.1)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PlatformAdmin, PlatformAuditLog
from app.services.admin import auth
from app.services.admin.access import disable, grant_access
from tests.api.admin_helpers import ADMIN_EMAIL, ADMIN_PASSWORD, activate, code

Factory = Callable[[], TestClient]
REFUSED = {"error": {"code": "invalid_credentials", "message": "Identifiants ou code incorrects."}}
BAD_LINK = "Lien invalide ou expiré. Relancez la commande sur le serveur."


class Clock:
    """The service's clock, moved by the test."""

    def __init__(self) -> None:
        self.now = datetime.now(UTC).replace(microsecond=0)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(auth, "_now", c)
    return c


def sign_in(
    client: TestClient,
    code_: str,
    *,
    email: str = ADMIN_EMAIL,
    password: str = ADMIN_PASSWORD,
) -> Response:
    return client.post(
        "/admin/auth/login", json={"email": email, "password": password, "code": code_}
    )


def actions(db: Session) -> list[str]:
    return list(db.scalars(select(PlatformAuditLog.action).order_by(PlatformAuditLog.at)))


def test_activation_end_to_end(make_client: Factory, db: Session) -> None:
    c = make_client()
    token = grant_access(db, ADMIN_EMAIL, "Admin")
    assert c.post("/admin/auth/setup/lookup", json={"token": token}).json() == {
        "email": ADMIN_EMAIL
    }
    short = c.post("/admin/auth/setup/password", json={"token": token, "password": "court"})
    assert short.status_code == 422
    s = c.post(
        "/admin/auth/setup/password", json={"token": token, "password": ADMIN_PASSWORD}
    ).json()
    assert s["qr_svg"].lstrip().startswith("<svg") and s["secret"] in s["otpauth_uri"]
    bad = c.post("/admin/auth/setup/confirm", json={"token": token, "code": "000000"})
    assert bad.status_code == 400
    assert bad.json()["error"] == {
        "code": "invalid_code",
        "message": "Code incorrect. Vérifiez l'heure de votre téléphone.",
    }
    done = c.post("/admin/auth/setup/confirm", json={"token": token, "code": code(s["secret"])})
    assert done.status_code == 200, done.text
    assert len(done.json()["recovery_codes"]) == 8
    assert done.json()["me"] == {
        "email": ADMIN_EMAIL,
        "full_name": "Admin",
        "recovery_codes_left": 8,
        "previous_login_at": None,
    }
    assert c.get("/admin/auth/me").json()["email"] == ADMIN_EMAIL  # the session is open
    # the link is destroyed, the secrets are not stored in clear
    assert c.post("/admin/auth/setup/lookup", json={"token": token}).status_code == 404
    admin = db.scalar(select(PlatformAdmin))
    assert admin is not None and admin.totp_secret_enc and admin.password_hash
    assert s["secret"] not in admin.totp_secret_enc
    assert ADMIN_PASSWORD not in admin.password_hash
    assert len(admin.recovery_codes) == 8 and all(len(h) == 64 for h in admin.recovery_codes)
    assert not set(done.json()["recovery_codes"]) & set(admin.recovery_codes)
    assert actions(db) == ["access_reset", "setup_completed"]


def test_expired_link(make_client: Factory, db: Session) -> None:
    c = make_client()
    token = grant_access(db, ADMIN_EMAIL)
    admin = db.scalar(select(PlatformAdmin))
    assert admin is not None
    admin.setup_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    for path, body in (
        ("lookup", {"token": token}),
        ("password", {"token": token, "password": ADMIN_PASSWORD}),
        ("confirm", {"token": token, "code": "123456"}),
        ("lookup", {"token": "un-jeton-inconnu"}),
    ):
        res = c.post(f"/admin/auth/setup/{path}", json=body)
        assert res.status_code == 404, path
        assert res.json()["error"] == {"code": "invalid_setup_link", "message": BAD_LINK}


def test_reloaded_activation_page_keeps_only_the_last_secret(
    make_client: Factory, db: Session
) -> None:
    c = make_client()
    token = grant_access(db, ADMIN_EMAIL)
    body = {"token": token, "password": ADMIN_PASSWORD}
    first = c.post("/admin/auth/setup/password", json=body).json()["secret"]
    second = c.post("/admin/auth/setup/password", json=body).json()["secret"]
    assert first != second
    stale = c.post("/admin/auth/setup/confirm", json={"token": token, "code": code(first)})
    assert stale.status_code == 400  # the link still works after a wrong code
    fresh = c.post("/admin/auth/setup/confirm", json={"token": token, "code": code(second)})
    assert fresh.status_code == 200


def test_confirming_before_choosing_a_password_is_refused(
    make_client: Factory, db: Session
) -> None:
    token = grant_access(db, ADMIN_EMAIL)
    res = make_client().post("/admin/auth/setup/confirm", json={"token": token, "code": "123456"})
    assert res.status_code == 400 and res.json()["error"]["code"] == "invalid_code"


def test_login_and_cookie(make_client: Factory, db: Session, clock: Clock) -> None:
    activated_at = clock.now
    secret, _ = activate(make_client(), db, when=clock.now)
    clock.advance(seconds=30)
    c = make_client()
    res = sign_in(c, code(secret, when=clock.now))
    assert res.status_code == 200, res.text
    cookie = res.headers["set-cookie"]
    assert cookie.startswith("pilao_admin_session=")
    for part in ("HttpOnly", "SameSite=strict", "Max-Age=43200", "Path=/"):
        assert part in cookie, part
    body = res.json()
    assert body["email"] == ADMIN_EMAIL and body["recovery_codes_left"] == 8
    assert datetime.fromisoformat(body["previous_login_at"]) == activated_at
    assert c.get("/admin/auth/me").json() == body
    assert make_client().get("/admin/auth/me").status_code == 401  # no cookie, no entry


def test_one_generic_refusal(make_client: Factory, db: Session, clock: Clock) -> None:
    secret, _ = activate(make_client(), db, when=clock.now)
    grant_access(db, "pas-active@pilao.test")  # an account whose activation was never done
    clock.advance(seconds=30)
    c = make_client()
    good = code(secret, when=clock.now)
    wrong_code = f"{(int(good) + 1) % 1_000_000:06d}"
    attempts = [
        sign_in(c, good, password="un-mauvais-mot-de-passe"),
        sign_in(c, wrong_code),
        sign_in(c, good, email="inconnu@pilao.test"),
        sign_in(c, good, email="pas-active@pilao.test"),
    ]
    disable(db, ADMIN_EMAIL)
    attempts.append(sign_in(c, good))
    for res in attempts:
        assert res.status_code == 401 and res.json() == REFUSED
        assert "set-cookie" not in res.headers
    assert actions(db).count("login_failed") == 5


def test_a_code_works_once(make_client: Factory, db: Session, clock: Clock) -> None:
    secret, _ = activate(make_client(), db, when=clock.now)
    c = make_client()
    # the code that activated the account cannot sign in: same time step
    assert sign_in(c, code(secret, when=clock.now)).status_code == 401
    following = code(secret, 1, when=clock.now)
    assert sign_in(c, following).status_code == 200  # the next step is within the window
    assert sign_in(make_client(), following).status_code == 401  # replayed


def test_typed_code_with_spaces(make_client: Factory, db: Session, clock: Clock) -> None:
    secret, _ = activate(make_client(), db, when=clock.now)
    clock.advance(seconds=30)
    good = code(secret, when=clock.now)
    assert sign_in(make_client(), f" {good[:3]} {good[3:]} ").status_code == 200


def test_recovery_code_once_any_case(make_client: Factory, db: Session, clock: Clock) -> None:
    _, codes = activate(make_client(), db, when=clock.now)
    typed = codes[0].replace("-", "").upper()
    c = make_client()
    # a wrong password never burns a recovery code
    assert sign_in(c, typed, password="un-mauvais-mot-de-passe").status_code == 401
    res = sign_in(c, typed)
    assert res.status_code == 200 and res.json()["recovery_codes_left"] == 7
    assert sign_in(make_client(), codes[0]).status_code == 401  # used once
    assert sign_in(make_client(), codes[1]).status_code == 200
    assert actions(db).count("recovery_code_used") == 2


def test_lock_after_five_failures(make_client: Factory, db: Session, clock: Clock) -> None:
    secret, _ = activate(make_client(), db, when=clock.now)
    clock.advance(seconds=30)
    c = make_client()
    for _ in range(5):
        res = sign_in(c, code(secret, when=clock.now), password="un-mauvais-mot-de-passe")
        assert res.status_code == 401
    locked = sign_in(c, code(secret, when=clock.now))  # even with the right credentials
    assert locked.status_code == 429
    assert locked.json()["error"] == {
        "code": "too_many_attempts",
        "message": "Trop de tentatives. Réessayez dans quelques minutes.",
    }
    clock.advance(minutes=16)
    assert sign_in(c, code(secret, when=clock.now)).status_code == 200


def test_session_ends(make_client: Factory, db: Session, clock: Clock) -> None:
    c = make_client()
    secret, _ = activate(c, db, when=clock.now)
    assert c.get("/admin/auth/me").status_code == 200
    assert c.post("/admin/auth/logout").status_code == 200
    assert c.get("/admin/auth/me").status_code == 401

    clock.advance(seconds=30)
    assert sign_in(c, code(secret, when=clock.now)).status_code == 200
    clock.advance(hours=12, seconds=1)
    assert c.get("/admin/auth/me").status_code == 401  # 12 hours, never extended

    assert sign_in(c, code(secret, when=clock.now)).status_code == 200
    assert disable(db, ADMIN_EMAIL)
    assert c.get("/admin/auth/me").status_code == 401
    assert actions(db).count("logout") == 1


def test_previous_login(make_client: Factory, db: Session, clock: Clock) -> None:
    c = make_client()
    t0 = clock.now
    secret, _ = activate(c, db, when=clock.now)
    assert c.get("/admin/auth/me").json()["previous_login_at"] is None
    clock.advance(minutes=5)
    first = sign_in(c, code(secret, when=clock.now)).json()
    assert datetime.fromisoformat(first["previous_login_at"]) == t0
    clock.advance(minutes=5)
    second = sign_in(c, code(secret, when=clock.now)).json()
    assert datetime.fromisoformat(second["previous_login_at"]) == t0 + timedelta(minutes=5)
