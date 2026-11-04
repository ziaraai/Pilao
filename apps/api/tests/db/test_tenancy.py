import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.tenancy import TenancyViolation, scope_session
from app.db.models import AuditLog, File, Job, Organization, User


def make_org(db: Session, n: int) -> Organization:
    org = Organization(siren=f"{n:09d}", siret=f"{n:014d}", name=f"Org {n}")
    db.add(org)
    db.flush()
    return org


def make_file(db: Session, org: Organization, key: str) -> File:
    f = File(
        org_id=org.id,
        storage_key=key,
        filename="a.pdf",
        mime="application/pdf",
        size_bytes=1,
        sha256="0" * 64,
    )
    db.add(f)
    db.flush()
    return f


def test_scoped_session_only_sees_own_org(db: Session) -> None:
    a, b = make_org(db, 1), make_org(db, 2)
    make_file(db, a, "a/1")
    make_file(db, b, "b/1")
    db.expunge_all()

    assert len(db.scalars(select(File)).all()) == 2  # unscoped (platform) session

    scope_session(db, a.id)
    files = db.scalars(select(File)).all()
    assert [f.storage_key for f in files] == ["a/1"]


def test_scoped_session_cannot_get_other_org_row_by_id(db: Session) -> None:
    a, b = make_org(db, 1), make_org(db, 2)
    other = make_file(db, b, "b/1")
    db.expunge_all()
    scope_session(db, a.id)
    assert db.get(File, other.id) is None


def test_scoped_session_cannot_update_or_delete_other_org(db: Session) -> None:
    from sqlalchemy import delete, update

    a, b = make_org(db, 1), make_org(db, 2)
    other = make_file(db, b, "b/1")
    scope_session(db, a.id)
    assert db.execute(update(File).values(filename="x")).rowcount == 0
    assert db.execute(delete(File)).rowcount == 0
    scope_session(db, b.id)
    assert db.get(File, other.id) is not None


def test_insert_defaults_to_session_org_and_rejects_foreign_org(db: Session) -> None:
    a, b = make_org(db, 1), make_org(db, 2)
    scope_session(db, a.id)
    f = File(storage_key="k", filename="a", mime="x", size_bytes=1, sha256="0" * 64)
    db.add(f)
    db.flush()
    assert f.org_id == a.id
    db.add(
        File(org_id=b.id, storage_key="k2", filename="a", mime="x", size_bytes=1, sha256="0" * 64)
    )
    with pytest.raises(TenancyViolation):
        db.flush()


def test_platform_jobs_invisible_to_tenants(db: Session) -> None:
    a = make_org(db, 1)
    db.add_all([Job(kind="import_boamp"), Job(kind="analyze_dce", org_id=a.id)])
    db.flush()
    scope_session(db, a.id)
    assert [j.kind for j in db.scalars(select(Job)).all()] == ["analyze_dce"]


def test_email_is_case_insensitive_unique(db: Session) -> None:
    a = make_org(db, 1)
    db.add(User(org_id=a.id, email="Bob@Example.com", role="org_admin"))
    db.flush()
    db.add(User(org_id=a.id, email="bob@example.com", role="org_member"))
    with pytest.raises(IntegrityError):
        db.flush()


def test_invalid_role_and_job_status_rejected(db: Session) -> None:
    a = make_org(db, 1)
    db.add(User(org_id=a.id, email="x@y.fr", role="root"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()
    db.add(Job(kind="k", status="stuck"))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_scoped_session_does_not_serve_other_org_rows_from_identity_map(db: Session) -> None:
    a, b = make_org(db, 1), make_org(db, 2)
    other = make_file(db, b, "b/1")  # loaded while unscoped: sits in the identity map
    scope_session(db, a.id)
    assert db.get(File, other.id) is None
    assert db.get(Organization, b.id) is None


def test_scoped_session_only_sees_own_organization(db: Session) -> None:
    a, _ = make_org(db, 1), make_org(db, 2)
    db.expunge_all()
    scope_session(db, a.id)
    assert [o.id for o in db.scalars(select(Organization)).all()] == [a.id]


def test_scoped_session_cannot_move_a_row_to_another_org(db: Session) -> None:
    a, b = make_org(db, 1), make_org(db, 2)
    own = make_file(db, a, "a/1")
    scope_session(db, a.id)
    own.org_id = b.id
    with pytest.raises(TenancyViolation):
        db.flush()


def test_scoped_statements_cannot_assign_another_org(db: Session) -> None:
    from sqlalchemy import insert, update

    a, b = make_org(db, 1), make_org(db, 2)
    make_file(db, a, "a/1")
    scope_session(db, a.id)
    with pytest.raises(TenancyViolation):
        db.execute(update(File).values(org_id=b.id))
    row = {"storage_key": "z", "filename": "a", "mime": "x", "size_bytes": 1, "sha256": "0" * 64}
    with pytest.raises(TenancyViolation):
        db.execute(insert(File), [{**row, "org_id": b.id}])
    with pytest.raises(TenancyViolation):
        db.execute(insert(File).values(**row, org_id=b.id))
    db.execute(insert(File), [{**row, "org_id": a.id}])  # own org: allowed


def test_deleting_org_cascades(db: Session) -> None:
    a = make_org(db, 1)
    u = User(org_id=a.id, email="x@y.fr", role="org_admin")
    db.add(u)
    db.flush()
    make_file(db, a, "a/1")
    db.add(AuditLog(org_id=a.id, user_id=u.id, action="create", entity="file", meta={"k": 1}))
    db.add(Job(org_id=a.id, kind="k", ref_id=uuid.uuid4()))
    db.flush()
    db.execute(text("DELETE FROM organizations WHERE id = :i"), {"i": a.id})
    for table in ("users", "files", "audit_logs", "jobs"):
        assert db.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0
