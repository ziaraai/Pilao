"""Row-level multi-tenancy, enforced in the ORM layer.

Call :func:`scope_session` once per request/job. From then on:

* every SELECT/UPDATE/DELETE on a ``TenantOwned`` model is filtered by ``org_id``
  (even if a developer forgets the ``where``), joined/relationship loads included;
* inserting a row for another organization raises :class:`TenancyViolation`.

An unscoped session (no ``org_id``) is only for auth, platform jobs and back-office.
"""

import uuid

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.db.base import Base, TenantOwned

_KEY = "org_id"


class TenancyViolation(Exception):
    """A write targeted an organization other than the session's organization."""


def _tenant_models() -> list[type[TenantOwned]]:
    return [m.class_ for m in Base.registry.mappers if issubclass(m.class_, TenantOwned)]


def scope_session(session: Session, org_id: uuid.UUID) -> Session:
    session.info[_KEY] = org_id
    return session


@event.listens_for(Session, "do_orm_execute")
def _filter_by_org(state: ORMExecuteState) -> None:
    org_id = state.session.info.get(_KEY)
    if org_id is None or state.is_column_load or state.is_relationship_load:
        return
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            *(
                with_loader_criteria(model, model.org_id == org_id, include_aliases=True)
                for model in _tenant_models()
            )
        )


@event.listens_for(Session, "before_flush")
def _check_writes(session: Session, *_: object) -> None:
    org_id = session.info.get(_KEY)
    if org_id is None:
        return
    for obj in session.new:
        if isinstance(obj, TenantOwned):
            if obj.org_id is None:
                obj.org_id = org_id
            elif obj.org_id != org_id:
                raise TenancyViolation(f"{type(obj).__name__} written for another org")
