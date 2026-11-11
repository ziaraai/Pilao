"""A suspended company (lot 2 of the administration, spec §2.2): nobody gets in, nothing leaves.

The suspension itself is set by the administration (tested in ``test_admin_accounts``); here
it is written directly in the database to check every way into the company space.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Organization, TenderMatch, User
from app.services.alerts import run_daily
from tests.api.helpers import PASSWORD, register_payload, signed_in_client
from tests.api.test_alerts import mails_to, paris
from tests.api.test_tenders import (  # noqa: F401 - the scorer fixture
    Factory,
    ScoreModel,
    company,
    load,
    notice,
    scorer,
)
from tests.api.test_vault import TODAY, confirm, deposit
from tests.conftest import FakeQueue, Outbox

MESSAGE = "L'accès de votre entreprise à Pilao est suspendu. Contactez Pilao."


def org_of(db: Session, email: str) -> Organization:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    return db.get_one(Organization, user.org_id)


def suspend(db: Session, email: str) -> Organization:
    org = org_of(db, email)
    org.suspended_at = datetime.now(UTC)
    org.suspension_reason = "Test"
    db.commit()
    return org


def login(make_client: Factory, email: str, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return make_client().post("/auth/login", json={"email": email, "password": password})


def test_login_refused_after_right_password_only(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    signed_in_client(make_client, outbox)
    suspend(db, "user1@example.fr")

    res = login(make_client, "user1@example.fr")
    assert res.status_code == 403
    assert res.json()["error"] == {"code": "account_suspended", "message": MESSAGE}
    wrong = login(make_client, "user1@example.fr", "not-the-password")
    assert wrong.status_code == 401  # a suspended account does not show itself
    assert wrong.json()["error"]["message"] == "E-mail ou mot de passe incorrect."


def test_open_session_refused(make_client: Factory, outbox: Outbox, db: Session) -> None:
    c = signed_in_client(make_client, outbox)
    assert c.get("/auth/me").status_code == 200
    suspend(db, "user1@example.fr")

    res = c.get("/auth/me")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "account_suspended"
    assert c.get("/profile").status_code == 403


def test_message_names_support_email(
    make_client: Factory, outbox: Outbox, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "support_email", "aide@pilao.test")
    signed_in_client(make_client, outbox)
    suspend(db, "user1@example.fr")

    res = login(make_client, "user1@example.fr")
    assert res.json()["error"]["message"] == (
        "L'accès de votre entreprise à Pilao est suspendu. Contactez Pilao : aide@pilao.test."
    )


def test_invitation_link_refused(make_client: Factory, outbox: Outbox, db: Session) -> None:
    c = signed_in_client(make_client, outbox)
    invited = c.post("/organization/members", json={"email": "collegue@example.fr"})
    assert invited.status_code == 201, invited.text
    token = outbox.last_token()
    suspend(db, "user1@example.fr")

    lookup = make_client().post("/auth/invitations/lookup", json={"token": token})
    assert lookup.status_code == 403
    assert lookup.json()["error"]["code"] == "account_suspended"
    accept = make_client().post(
        "/auth/invitations/accept",
        json={"token": token, "full_name": "Col", "password": PASSWORD, "accept_terms": True},
    )
    assert accept.status_code == 403


def test_verify_email_refused_and_resend_silent(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    client = make_client()
    assert client.post("/auth/register", json=register_payload(3)).status_code == 201
    token = outbox.last_token()
    suspend(db, "user3@example.fr")

    res = client.post("/auth/verify-email", json={"token": token})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "account_suspended"
    before = len(outbox.sent)
    resend = client.post("/auth/resend-verification", json={"email": "user3@example.fr"})
    assert resend.status_code == 200
    assert len(outbox.sent) == before


def test_watch_skips_suspended(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    scorer: ScoreModel,  # noqa: F811
    db: Session,
) -> None:
    company(make_client, outbox, queue, min_score_alert=10)
    company(make_client, outbox, queue, 2, min_score_alert=10)
    suspended = suspend(db, "user2@example.fr")
    scorer.scores = {"Nettoyage A": 85}

    load(db, queue, outbox, notice("A"))
    owners = set(db.scalars(select(TenderMatch.org_id)))
    assert owners == {org_of(db, "user1@example.fr").id}  # nothing scored for the suspended

    today = datetime.now(paris(TODAY, 8).tzinfo).date()
    run_daily(db, outbox, paris(today, 8))
    assert any(s.startswith("Pilao —") for s, _ in mails_to(outbox, "user1@example.fr"))
    assert not any(s.startswith("Pilao —") for s, _ in mails_to(outbox, "user2@example.fr"))
    assert suspended.suspended_at is not None


def test_expiry_alerts_skip_suspended(
    make_client: Factory, outbox: Outbox, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "session_ttl_hours", 24 * 60)
    c = signed_in_client(make_client, outbox)
    doc = deposit(c).json()["id"]
    assert confirm(c, doc, valid_until=(TODAY + timedelta(days=25)).isoformat()).status_code == 200
    suspend(db, "user1@example.fr")

    before = len(outbox.sent)
    run_daily(db, outbox, paris(TODAY, 6))
    assert outbox.sent[before:] == []
