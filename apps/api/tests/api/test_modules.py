"""The guard of each module's routes (lot 3, spec §5.2)."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Organization, User
from tests.api.helpers import signed_in_client
from tests.api.test_suspension import suspend
from tests.api.test_vault import PDF
from tests.conftest import Outbox

Factory = Callable[[], TestClient]
MESSAGE = "Ce module n'est pas activé pour votre entreprise. Contactez Pilao."
NOWHERE = uuid.uuid4()

# (module, method, path): one read and one write of each module's routers
ROUTES = [
    ("veille", "get", "/tenders"),
    ("veille", "post", f"/tenders/{NOWHERE}/track"),
    ("reponse", "get", "/bids"),
    ("reponse", "post", "/bids"),
    ("reponse", "get", f"/bids/{NOWHERE}/memoir"),
    ("reponse", "get", f"/bids/{NOWHERE}/documents"),
    ("reponse", "get", "/vault"),
    ("reponse", "get", "/knowledge"),
    ("reponse", "get", "/profile/suggestions"),
    ("reponse", "post", "/profile/suggestions/read"),
]


def set_modules(db: Session, email: str, modules: list[str]) -> None:
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    org = db.get_one(Organization, user.org_id)
    org.modules = modules
    db.commit()


def test_me_lists_modules(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    assert c.get("/auth/me").json()["modules"] == ["veille", "reponse"]


def test_me_gives_the_support_address(
    make_client: Factory, outbox: Outbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The card « Ce module n'est pas activé » says whom to write to (spec §3.2)."""
    c = signed_in_client(make_client, outbox)
    monkeypatch.setattr(get_settings(), "support_email", None)
    assert c.get("/auth/me").json()["support_email"] is None
    monkeypatch.setattr(get_settings(), "support_email", "aide@pilao.test")
    assert c.get("/auth/me").json()["support_email"] == "aide@pilao.test"


@pytest.mark.parametrize(("module", "method", "path"), ROUTES)
def test_disabled_module_refused(
    make_client: Factory, outbox: Outbox, db: Session, module: str, method: str, path: str
) -> None:
    c = signed_in_client(make_client, outbox)
    with_it = c.request(method, path, json={"title": "Dossier"} if path == "/bids" else None)
    assert with_it.status_code != 403, with_it.text

    other = "reponse" if module == "veille" else "veille"
    set_modules(db, "user1@example.fr", [other])
    res = c.request(method, path, json={"title": "Dossier"} if path == "/bids" else None)
    assert res.status_code == 403
    assert res.json()["error"] == {"code": "module_disabled", "message": MESSAGE}


def test_message_names_support_email(
    make_client: Factory, outbox: Outbox, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "support_email", "aide@pilao.test")
    c = signed_in_client(make_client, outbox)
    set_modules(db, "user1@example.fr", [])
    assert c.get("/bids").json()["error"]["message"] == (
        "Ce module n'est pas activé pour votre entreprise. Contactez Pilao : aide@pilao.test."
    )


def test_neighbour_keeps_its_module(make_client: Factory, outbox: Outbox, db: Session) -> None:
    a = signed_in_client(make_client, outbox)
    b = signed_in_client(make_client, outbox, 2)
    set_modules(db, "user1@example.fr", ["veille"])
    assert a.get("/bids").status_code == 403
    assert b.get("/bids").status_code == 200


def test_order_of_refusals(make_client: Factory, outbox: Outbox, db: Session) -> None:
    c = signed_in_client(make_client, outbox)
    set_modules(db, "user1@example.fr", [])
    suspend(db, "user1@example.fr")
    assert c.get("/bids").json()["error"]["code"] == "account_suspended"


def test_common_routes_stay_open(make_client: Factory, outbox: Outbox, db: Session) -> None:
    c = signed_in_client(make_client, outbox)
    set_modules(db, "user1@example.fr", [])
    for path in ("/profile", "/dashboard", "/organization/members", "/auth/me"):
        assert c.get(path).status_code == 200, path
    upload = c.post("/files", files={"file": ("logo.pdf", PDF, "application/pdf")})
    assert upload.status_code == 201, upload.text
    assert c.get("/auth/me").json()["modules"] == []
