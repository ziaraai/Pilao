"""The company rules run on behalf of Pilao (lot 2, spec §4.1): same rules, another author."""

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.tenancy import scope_session
from app.db.models import (
    AuditLog,
    DataRequest,
    Organization,
    PlatformAdmin,
    PurgeLog,
    User,
    UserSession,
)
from app.schemas.members import InviteIn
from app.services import members, org_data
from app.services.actors import PILAO_NAME, PlatformActor
from app.services.admin.access import grant_access
from tests.api.helpers import PASSWORD, signed_in_client
from tests.api.test_vault import deposit
from tests.conftest import MemoryStorage, Outbox

Factory = Callable[[], TestClient]


def pilao(db: Session) -> PlatformActor:
    grant_access(db, "admin@pilao.test", "Admin")
    admin = db.scalar(select(PlatformAdmin).where(PlatformAdmin.email == "admin@pilao.test"))
    assert admin is not None
    return PlatformActor(admin_id=admin.id, email=admin.email)


def company(db: Session, email: str = "user1@example.fr") -> tuple[Organization, User]:
    """The company of ``email``, with ``db`` scoped to it as an administration route does."""
    user = db.scalar(select(User).where(User.email == email))
    assert user is not None
    org = db.get_one(Organization, user.org_id)
    scope_session(db, org.id)
    return org, user


def test_pilao_invites(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    actor = pilao(db)
    org, _ = company(db)

    first = members.invite(
        db,
        actor,
        org,
        InviteIn(email="patron@example.fr", full_name="Jean Patron", role="org_admin"),
        outbox,
        first_access=True,
    )
    mail = outbox.sent[-1]
    assert mail.to == "patron@example.fr"
    assert mail.subject == f"Pilao a ouvert l'espace de {org.name}"
    assert "L'équipe Pilao a ouvert l'espace de" in mail.body and "invitation?token=" in mail.body

    members.invite(db, actor, org, InviteIn(email="collegue@example.fr"), outbox)
    assert outbox.sent[-1].subject == f"{PILAO_NAME} vous invite sur Pilao ({org.name})"

    entry = db.scalar(
        select(AuditLog).where(AuditLog.action == "invite", AuditLog.entity_id == first.id)
    )
    assert entry is not None and entry.user_id is None and entry.meta == {"by": "pilao"}


def test_pilao_keeps_last_admin_rule(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    actor = pilao(db)
    _, admin = company(db)

    with pytest.raises(ApiError) as demoted:
        members.change_role(db, actor, admin.id, "org_member")
    assert demoted.value.code == "last_admin"
    with pytest.raises(ApiError) as removed:
        members.remove(db, actor, admin.id)  # not « your own access »: Pilao is nobody's colleague
    assert removed.value.code == "last_admin"
    assert removed.value.message == "L'entreprise doit garder au moins un administrateur."


def test_pilao_schedules_deletion(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    actor = pilao(db)
    org, _ = company(db)

    req = org_data.request_deletion(db, actor, org, org.name, outbox)
    assert req.requested_by is None and req.platform_admin_id == actor.admin_id
    mail = outbox.sent[-1]
    assert mail.to == "user1@example.fr"
    assert mail.subject.startswith(f"Suppression des données de {org.name} programmée le ")
    assert f"Pilao a programmé la suppression de toutes les données de {org.name}" in mail.body
    assert "Pour toute question, contactez Pilao." in mail.body

    org_data.cancel_deletion(db, actor, org, outbox)
    assert db.get_one(DataRequest, req.id).status == "cancelled"
    assert outbox.sent[-1].subject == f"Suppression des données de {org.name} annulée"
    assert "Pilao a annulé la suppression des données" in outbox.sent[-1].body

    with pytest.raises(ApiError) as mismatch:
        org_data.check_confirmation(org, "Autre nom")
    assert mismatch.value.code == "confirmation_mismatch"


def test_logout_everywhere(make_client: Factory, outbox: Outbox, db: Session) -> None:
    first = signed_in_client(make_client, outbox)
    second = make_client()
    assert (
        second.post(
            "/auth/login", json={"email": "user1@example.fr", "password": PASSWORD}
        ).status_code
        == 200
    )
    actor = pilao(db)
    _, user = company(db)

    assert members.logout_everywhere(db, actor, user.id) == 2
    assert first.get("/auth/me").status_code == 401
    assert second.get("/auth/me").status_code == 401
    open_ = db.scalars(select(UserSession).where(UserSession.revoked_at.is_(None))).all()
    assert open_ == []


def test_erase_organization_without_mail(
    make_client: Factory, outbox: Outbox, storage: MemoryStorage, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    assert deposit(c).status_code == 201
    assert storage.objects
    user = db.scalar(select(User).where(User.email == "user1@example.fr"))
    assert user is not None
    org_id: uuid.UUID = user.org_id
    before = len(outbox.sent)

    assert org_data.erase_organization(db, org_id, storage, requested_at=None) is True
    assert storage.objects == {}
    assert db.get(Organization, org_id) is None
    proof = db.scalar(select(PurgeLog).where(PurgeLog.org_id == org_id))
    assert proof is not None and proof.objects == 1
    assert len(outbox.sent) == before
