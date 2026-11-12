"""The administration and the company space never open each other's doors (ADR-040)."""

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.admin_deps import read_only
from app.core.config import get_settings
from app.db.models import (
    CompanyReference,
    DceFile,
    DcePage,
    DceVersion,
    DocumentChunk,
    Equipment,
    File,
    KnowledgeDocument,
    Organization,
)
from app.schemas.admin import OverviewOut
from app.services.admin import supervision
from tests.api.admin_helpers import activated_admin, org_named, seed_bid, seed_memoir
from tests.api.helpers import signed_in_client
from tests.conftest import Outbox

Factory = Callable[[], TestClient]

ADMIN_GETS = [
    "/admin/auth/me",
    "/admin/overview",
    "/admin/organizations",
    "/admin/ai-costs",
    "/admin/system",
    "/admin/feedback",
    "/admin/audit",
    "/admin/modules",
    "/admin/plans",
    "/admin/credit-prices",
    "/admin/settings",
]


def test_company_session_is_refused_everywhere(make_client: Factory, outbox: Outbox) -> None:
    company = signed_in_client(make_client, outbox)
    for path in ADMIN_GETS:
        assert company.get(path).status_code == 401, path
    # a company token presented under the admin cookie's name opens nothing either
    intruder = make_client()
    intruder.cookies.set("pilao_admin_session", company.cookies["pilao_session"])
    for path in ADMIN_GETS:
        assert intruder.get(path).status_code == 401, path


def test_company_session_cannot_act_on_accounts(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    company = signed_in_client(make_client, outbox)
    org = org_named(db, "Entreprise 1").id
    user = uuid.uuid4()
    for method, path in [
        ("post", "/admin/organizations"),
        ("post", f"/admin/organizations/{org}/suspend"),
        ("post", f"/admin/organizations/{org}/reactivate"),
        ("get", f"/admin/organizations/{org}/deletion"),
        ("post", f"/admin/organizations/{org}/deletion"),
        ("delete", f"/admin/organizations/{org}/deletion"),
        ("post", f"/admin/organizations/{org}/users"),
        ("post", f"/admin/organizations/{org}/users/{user}/invitation"),
        ("post", f"/admin/organizations/{org}/users/{user}/verification"),
        ("post", f"/admin/organizations/{org}/users/{user}/password-reset"),
        ("patch", f"/admin/organizations/{org}/users/{user}"),
        ("post", f"/admin/organizations/{org}/users/{user}/logout"),
        ("post", f"/admin/organizations/{org}/users/{user}/remove"),
        ("put", f"/admin/organizations/{org}/modules/reponse"),
        ("put", f"/admin/organizations/{org}/plan"),
        ("post", f"/admin/organizations/{org}/credits"),
        ("get", f"/admin/organizations/{org}/credits"),
        ("get", "/admin/companies/lookup?siret=12345678901234"),
    ]:
        assert company.request(method, path, json={}).status_code == 401, path
    db.expire_all()
    assert org_named(db, "Entreprise 1").suspended_at is None
    assert org_named(db, "Entreprise 1").modules == ["veille", "reponse"]


def test_admin_session_is_refused_in_the_company_space(make_client: Factory, db: Session) -> None:
    admin, _ = activated_admin(make_client, db)
    for path in ("/auth/me", "/profile", "/bids", "/dashboard"):
        assert admin.get(path).status_code == 401, path
    intruder = make_client()
    intruder.cookies.set("pilao_session", admin.cookies["pilao_admin_session"])
    assert intruder.get("/auth/me").status_code == 401


def test_read_only_session_refuses_writes(db: Session) -> None:
    ro = read_only(db)
    with pytest.raises(DBAPIError, match="read-only"):
        ro.execute(text("update organizations set name = name"))
    db.rollback()


def test_cross_origin_post_is_refused(make_client: Factory, db: Session) -> None:
    admin, _ = activated_admin(make_client, db)
    res = admin.post("/admin/auth/logout", headers={"Origin": "https://ailleurs.example"})
    assert res.status_code == 403
    assert admin.get("/admin/auth/me").status_code == 200  # still signed in


def test_read_only_ends_with_the_request(make_client: Factory, outbox: Outbox, db: Session) -> None:
    """A supervision request must not leave the connection read-only for the next one."""
    company = signed_in_client(make_client, outbox)
    admin, _ = activated_admin(make_client, db)
    assert admin.get("/admin/overview").status_code == 200
    saved = company.put("/profile", json={"departments": ["69"]})
    assert saved.status_code == 200, saved.text
    assert admin.get(f"/admin/organizations/{org_named(db, 'Entreprise 1').id}").status_code == 200
    assert company.put("/profile", json={"departments": ["42"]}).status_code == 200


def test_supervision_routes_cannot_write(
    make_client: Factory, outbox: Outbox, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even a bug that writes from a supervision route is stopped by PostgreSQL."""
    signed_in_client(make_client, outbox)
    admin, _ = activated_admin(make_client, db)

    def buggy(session: Session, now: datetime) -> OverviewOut:
        session.execute(update(Organization).values(name="Piratée"))
        raise AssertionError("the write went through")

    monkeypatch.setattr(supervision, "overview", buggy)
    with pytest.raises(DBAPIError, match="read-only"):
        admin.get("/admin/overview")
    db.expire_all()
    assert org_named(db, "Entreprise 1").name == "Entreprise 1"


CANARY = "TEMOIN-CONFIDENTIEL-4f2a"


def _hide_canary_everywhere(db: Session, org_id: uuid.UUID) -> None:
    """The canary in every place a super admin must never read."""
    bid = seed_bid(db, org_id, title=f"Dossier {CANARY}", buyer_name=f"Acheteur {CANARY}")
    seed_memoir(db, bid, status="ready", content=f"Chapitre {CANARY}")
    stored: dict[str, Any] = {"mime": "application/pdf", "size_bytes": 10, "sha256": "0" * 64}
    dce = File(org_id=org_id, storage_key=f"k/{uuid.uuid4()}", filename=f"{CANARY}.pdf", **stored)
    doc = File(org_id=org_id, storage_key=f"k/{uuid.uuid4()}", filename=f"{CANARY}.docx", **stored)
    db.add_all([dce, doc])
    db.flush()
    version = DceVersion(org_id=org_id, bid_id=bid.id, version=2, status="ready")
    db.add(version)
    db.flush()
    piece = DceFile(
        org_id=org_id,
        dce_version_id=version.id,
        file_id=dce.id,
        path=f"{CANARY}.pdf",
        sha256="0" * 64,
    )
    db.add(piece)
    db.flush()
    db.add(DcePage(org_id=org_id, dce_file_id=piece.id, page=1, text=f"Article 1 {CANARY}"))
    memoir_doc = KnowledgeDocument(
        org_id=org_id, file_id=doc.id, kind="past_memoir", title=f"Mémoire {CANARY}", status="ready"
    )
    db.add(memoir_doc)
    db.flush()
    db.add(
        DocumentChunk(
            org_id=org_id,
            source_type="knowledge",
            source_id=memoir_doc.id,
            position=0,
            content=f"Passage {CANARY}",
            content_hash="h",
            tokens=3,
            embedding=[0.0] * get_settings().embedding_dim,
        )
    )
    db.add(Equipment(org_id=org_id, name=f"Autolaveuse {CANARY}", quantity=2))
    db.add(
        CompanyReference(
            org_id=org_id, client_name=f"Client {CANARY}", client_type="public", title=CANARY
        )
    )
    db.commit()


def test_no_customer_content_ever_leaves(make_client: Factory, outbox: Outbox, db: Session) -> None:
    company = signed_in_client(make_client, outbox)
    org_id = org_named(db, "Entreprise 1").id
    _hide_canary_everywhere(db, org_id)
    assert CANARY in company.get("/bids").text  # it is there, and the company sees it
    assert CANARY in company.get("/profile/equipment").text
    admin, _ = activated_admin(make_client, db)

    for path in [*ADMIN_GETS, f"/admin/organizations/{org_id}"]:
        res = admin.get(path)
        assert res.status_code == 200, path
        assert CANARY not in res.text, path
