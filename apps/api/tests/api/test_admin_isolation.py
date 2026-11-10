"""The administration and the company space never open each other's doors (ADR-040)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.admin_deps import read_only
from tests.api.admin_helpers import activated_admin
from tests.api.helpers import signed_in_client
from tests.conftest import Outbox

Factory = Callable[[], TestClient]

ADMIN_GETS = ["/admin/auth/me"]


def test_company_session_is_refused_everywhere(make_client: Factory, outbox: Outbox) -> None:
    company = signed_in_client(make_client, outbox)
    for path in ADMIN_GETS:
        assert company.get(path).status_code == 401, path
    # a company token presented under the admin cookie's name opens nothing either
    intruder = make_client()
    intruder.cookies.set("pilao_admin_session", company.cookies["pilao_session"])
    for path in ADMIN_GETS:
        assert intruder.get(path).status_code == 401, path


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
