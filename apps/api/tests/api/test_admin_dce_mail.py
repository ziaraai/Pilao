"""The DCE mailbox in the administration (ADR-055): switched on, its password tried then kept
encrypted (the authenticator code asked again), « Tester la connexion »."""

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import crypto, runtime
from app.core.config import get_settings
from app.db.models import PlatformSetting
from app.integrations.imap_mailbox import MailboxError, Waiting, get_mailbox_opener
from tests.api.helpers import signed_in_client
from tests.api.test_admin_accounts import admin, journal
from tests.conftest import Outbox

Factory = Callable[[], TestClient]
GOOD = "Boite-DCE-2026!"


class Box:
    def __init__(self) -> None:
        self.closed = False

    def waiting(self) -> list[Waiting]:
        return [Waiting("1", 10, False), Waiting("2", 10, True)]

    def close(self) -> None:
        self.closed = True


class Opener:
    def __init__(self) -> None:
        self.tried: list[str | None] = []
        self.down = False

    def __call__(self, password: str | None = None) -> Box:
        self.tried.append(password)
        if self.down:
            raise MailboxError("Serveur de messagerie injoignable (pilao.pro:993).")
        if password not in (None, GOOD):
            raise MailboxError("Connexion refusée : adresse ou mot de passe incorrect.")
        return Box()


@pytest.fixture
def opener(make_client: Factory, monkeypatch: pytest.MonkeyPatch) -> Iterator[Opener]:
    from app.main import app

    monkeypatch.setattr(get_settings(), "dce_mail_password", "")
    monkeypatch.setattr(get_settings(), "dce_mail_enabled", False)
    fake = Opener()
    app.dependency_overrides[get_mailbox_opener] = lambda: fake
    yield fake


def test_the_state_of_the_mailbox(make_client: Factory, db: Session, opener: Opener) -> None:
    client, _, _ = admin(make_client, db)
    box = client.get("/admin/settings").json()["dce_mail"]
    assert box == {
        "enabled": False,
        "origin": "server",
        "address": "dce@pilao.pro",
        "password_source": "none",  # never any part of the password itself
        "received_24h": 0,
        "to_sort": 0,
    }


def test_the_password_is_tried_then_kept_encrypted(
    make_client: Factory, db: Session, opener: Opener
) -> None:
    client, _, codes = admin(make_client, db)
    url = "/admin/settings/dce-mail/password"
    wrong = client.put(url, json={"password": "faux", "code": codes[0]})
    assert wrong.status_code == 422
    assert wrong.json()["error"]["message"] == (
        "Connexion refusée : adresse ou mot de passe incorrect."
    )
    assert db.get(PlatformSetting, "dce_mail.password") is None
    bad_code = client.put(url, json={"password": GOOD, "code": "000000"})
    assert bad_code.status_code == 400
    assert db.get(PlatformSetting, "dce_mail.password") is None

    res = client.put(url, json={"password": GOOD, "code": codes[1]})
    assert res.status_code == 200, res.text
    assert res.json()["password_source"] == "admin"
    row = db.get_one(PlatformSetting, "dce_mail.password")
    assert row.secret and GOOD not in row.secret
    assert crypto.decrypt(row.secret, "dce_mail.password") == GOOD
    assert GOOD not in res.text and GOOD not in client.get("/admin/settings").text
    assert runtime.secret("dce_mail.password") == GOOD
    assert len(journal(db, "dce_mail_password_replaced")) == 1
    assert opener.tried[-1] == GOOD


def test_switched_on_only_with_a_password(
    make_client: Factory, db: Session, opener: Opener
) -> None:
    client, _, codes = admin(make_client, db)
    url = "/admin/settings/dce-mail"
    refused = client.put(url, json={"enabled": True})
    assert refused.status_code == 409
    assert refused.json()["error"]["message"] == (
        "Enregistrez d'abord le mot de passe de la boîte."
    )
    client.put("/admin/settings/dce-mail/password", json={"password": GOOD, "code": codes[0]})
    res = client.put(url, json={"enabled": True})
    assert res.status_code == 200 and res.json()["enabled"] is True
    assert res.json()["origin"] == "admin"
    assert len(journal(db, "setting_changed")) == 1
    assert client.put(url, json={"enabled": False}).json()["enabled"] is False


def test_try_the_connection(make_client: Factory, db: Session, opener: Opener) -> None:
    client, _, codes = admin(make_client, db)
    url = "/admin/settings/dce-mail/test"
    none = client.post(url).json()
    assert none == {
        "ok": False,
        "waiting": 0,
        "flagged": 0,
        "error": "Le mot de passe de la boîte n'est pas enregistré.",
    }
    client.put("/admin/settings/dce-mail/password", json={"password": GOOD, "code": codes[0]})
    assert client.post(url).json() == {"ok": True, "waiting": 1, "flagged": 1, "error": None}
    opener.down = True
    down = client.post(url).json()
    assert down["ok"] is False and down["error"].startswith("Serveur de messagerie injoignable")


def test_back_to_the_server_password(
    make_client: Factory, db: Session, opener: Opener, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, codes = admin(make_client, db)
    client.put("/admin/settings/dce-mail/password", json={"password": GOOD, "code": codes[0]})
    assert client.delete("/admin/settings/dce-mail/password").status_code == 204
    box = client.get("/admin/settings").json()["dce_mail"]
    assert box["password_source"] == "none"
    monkeypatch.setattr(get_settings(), "dce_mail_password", "serveur")
    runtime.invalidate()
    assert client.get("/admin/settings").json()["dce_mail"]["password_source"] == "server"
    assert len(journal(db, "dce_mail_password_reset")) == 1


def test_company_session_refused(make_client: Factory, outbox: Outbox, opener: Opener) -> None:
    c = signed_in_client(make_client, outbox)
    for method, url in (
        ("put", "/admin/settings/dce-mail"),
        ("put", "/admin/settings/dce-mail/password"),
        ("delete", "/admin/settings/dce-mail/password"),
        ("post", "/admin/settings/dce-mail/test"),
    ):
        assert getattr(c, method)(url).status_code in (401, 403, 422), url
