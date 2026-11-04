"""Endpoint-level isolation: user of org A must get 404 on org B's resources.

A throw-away router models what every business router must do: take its DB session from
``ScopedDb`` / ``get_scoped_db``. When real routers exist, add them to ``ENDPOINTS``.
"""

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.deps import ScopedDb, require_admin
from app.core.errors import ApiError
from app.db.models import File, User
from app.main import app
from tests.api.helpers import signed_in_client
from tests.conftest import Outbox

router = APIRouter(prefix="/_test")


@router.post("/files", status_code=201)
def create_file(db: ScopedDb) -> dict[str, str]:
    f = File(storage_key=str(uuid.uuid4()), filename="a", mime="x", size_bytes=1, sha256="0" * 64)
    db.add(f)
    db.commit()
    return {"id": str(f.id), "org_id": str(f.org_id)}


@router.get("/files")
def list_files(db: ScopedDb) -> list[str]:
    return [str(i) for i in db.scalars(select(File.id))]


@router.get("/files/{file_id}")
def get_file(file_id: uuid.UUID, db: ScopedDb) -> dict[str, str]:
    f = db.get(File, file_id)
    if f is None:
        raise ApiError(404, "not_found", "Introuvable.")
    return {"id": str(f.id)}


@router.get("/admin-only")
def admin_only(_: Annotated[User, Depends(require_admin)]) -> dict[str, bool]:
    return {"ok": True}


app.include_router(router)


def test_org_a_cannot_see_or_fetch_org_b_files(
    make_client: Callable[[], TestClient], outbox: Outbox
) -> None:
    a = signed_in_client(make_client, outbox, 1)
    b = signed_in_client(make_client, outbox, 2)
    file_b = b.post("/_test/files").json()
    file_a = a.post("/_test/files").json()

    assert a.get(f"/_test/files/{file_b['id']}").status_code == 404
    assert a.get(f"/_test/files/{file_a['id']}").status_code == 200
    assert a.get("/_test/files").json() == [file_a["id"]]
    assert b.get("/_test/files").json() == [file_b["id"]]


def test_scoped_routes_require_authentication(make_client: Callable[[], TestClient]) -> None:
    anon = make_client()
    assert anon.get("/_test/files").status_code == 401
    assert anon.post("/_test/files").status_code == 401


def test_admin_dependency(make_client: Callable[[], TestClient], outbox: Outbox) -> None:
    a = signed_in_client(make_client, outbox, 1)
    assert a.get("/_test/admin-only").status_code == 200
