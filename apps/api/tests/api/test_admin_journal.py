"""Administration, lot 2: the journal screen (spec §2.6)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.admin import audit
from tests.api.admin_helpers import code
from tests.api.helpers import signed_in_client
from tests.api.test_admin_accounts import admin, create, org_id_of
from tests.conftest import Outbox

Factory = Callable[[], TestClient]


def actions(client: TestClient, **params: str) -> list[str]:
    res = client.get("/admin/audit", params=params)
    assert res.status_code == 200, res.text
    return [r["action"] for r in res.json()["rows"]]


def test_filters(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    signed_in_client(make_client, outbox, 2)
    org1, org2 = org_id_of(db, "user1@example.fr"), org_id_of(db, "user2@example.fr")
    client, _, _ = admin(make_client, db)
    client.get(f"/admin/organizations/{org1}")
    client.post(f"/admin/organizations/{org2}/suspend", json={"reason": "x"})

    assert actions(client, kind="logins") == ["setup_completed", "access_reset"]
    assert actions(client, kind="accounts") == ["organization_suspended", "organization_viewed"]
    assert actions(client, kind="all", org_id=org1) == ["organization_viewed"]
    rows = client.get("/admin/audit", params={"org_id": org2}).json()["rows"]
    assert rows[0]["org_name"] == "Entreprise 2" and rows[0]["meta"] == {"reason": "x"}
    assert rows[0]["admin_email"] == "admin@pilao.test"


def test_pagination(make_client: Factory, db: Session) -> None:
    client, _, _ = admin(make_client, db)
    start = datetime.now(UTC) - timedelta(days=1)
    for i in range(101):
        audit.record(
            db, "organization_viewed", email="x@pilao.test", at=start - timedelta(minutes=i)
        )
    db.commit()

    first = client.get("/admin/audit").json()
    assert len(first["rows"]) == 100 and first["next_cursor"] is not None
    second = client.get("/admin/audit", params={"cursor": first["next_cursor"]}).json()
    # 103 lines: the access granted, its activation, 101 company pages viewed
    assert len(second["rows"]) == 3
    assert second["next_cursor"] is None
    seen = [r["at"] for r in first["rows"] + second["rows"]]
    assert seen == sorted(seen, reverse=True) and len(set(seen)) == len(seen)


def test_deleted_company(make_client: Factory, db: Session) -> None:
    client, secret, _ = admin(make_client, db)
    org = create(client).json()["id"]
    res = client.post(
        f"/admin/organizations/{org}/deletion",
        json={"confirmation": "Propreté Test", "code": code(secret)},
    )
    assert res.status_code == 200

    rows = client.get("/admin/audit", params={"org_id": org}).json()["rows"]
    assert [r["action"] for r in rows] == ["organization_deleted", "organization_created"]
    assert all(r["org_name"] is None for r in rows)  # the company is gone, its trace stays


def test_pagination_with_equal_times(make_client: Factory, db: Session) -> None:
    """Lines written at the same instant (a recovery code and its sign-in) are all shown."""
    client, _, _ = admin(make_client, db)
    same = datetime.now(UTC) - timedelta(days=1)
    for _ in range(101):
        audit.record(db, "organization_viewed", email="x@pilao.test", at=same)
    db.commit()

    seen: list[str] = []
    params: dict[str, str] = {"kind": "accounts"}
    while True:
        page = client.get("/admin/audit", params=params).json()
        seen += [r["id"] for r in page["rows"]]
        if not page["next_cursor"]:
            break
        params["cursor"] = page["next_cursor"]
    assert len(seen) == 101 and len(set(seen)) == 101
