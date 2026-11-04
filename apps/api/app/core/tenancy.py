"""Row-level multi-tenancy, enforced in the ORM layer.

Call :func:`scope_session` once per request/job. From then on:

* every SELECT/UPDATE/DELETE on a ``TenantOwned`` model is filtered by ``org_id``
  (even if a developer forgets the ``where``), joined/relationship loads included;
  ``organizations`` itself is filtered down to the session's own organization;
* writing a row for another organization raises :class:`TenancyViolation`: unit-of-work
  inserts, updates and deletes, and ORM ``insert()``/``update()`` statements alike.

An unscoped session (no ``org_id``) is only for auth, platform jobs and back-office.
"""

import uuid
from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria
from sqlalchemy.sql.elements import BindParameter, ClauseElement

from app.db.base import Base, TenantOwned
from app.db.models.organization import Organization

_KEY = "org_id"


class TenancyViolation(Exception):
    """A write targeted an organization other than the session's organization."""


def _tenant_models() -> list[type[TenantOwned]]:
    return [m.class_ for m in Base.registry.mappers if issubclass(m.class_, TenantOwned)]


def _foreign(obj: object, org_id: uuid.UUID) -> bool:
    if isinstance(obj, TenantOwned):
        return obj.org_id != org_id
    if isinstance(obj, Organization):
        return obj.id != org_id
    return False


def scope_session(session: Session, org_id: uuid.UUID) -> Session:
    # Rows loaded before scoping (or under another scope) would otherwise still be served
    # from the identity map by ``session.get()`` without any SQL, hence without the filter.
    for obj in list(session.identity_map.values()):
        if _foreign(obj, org_id):
            session.expunge(obj)
    session.info[_KEY] = org_id
    return session


def _org_assignments(state: ORMExecuteState) -> Iterator[object]:
    """Every value an INSERT/UPDATE statement assigns to ``org_id``."""
    stmt: Any = state.statement
    rows: list[Mapping[Any, Any]] = [getattr(stmt, "_values", None) or {}]
    for batch in getattr(stmt, "_multi_values", None) or ():
        rows.extend(batch)
    params = state.parameters
    if isinstance(params, Mapping):
        rows.append(params)
    elif isinstance(params, Iterable):
        rows.extend(p for p in params if isinstance(p, Mapping))
    for row in rows:
        for key, value in row.items():
            if getattr(key, "key", key) == _KEY:
                yield value.value if isinstance(value, BindParameter) else value


@event.listens_for(Session, "do_orm_execute")
def _filter_by_org(state: ORMExecuteState) -> None:
    org_id = state.session.info.get(_KEY)
    if org_id is None or state.is_column_load or state.is_relationship_load:
        return
    if state.is_insert or state.is_update:
        for value in _org_assignments(state):
            if isinstance(value, ClauseElement) or value != org_id:
                raise TenancyViolation("statement assigns org_id of another org")
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            *(
                with_loader_criteria(model, model.org_id == org_id, include_aliases=True)
                for model in _tenant_models()
            ),
            with_loader_criteria(Organization, Organization.id == org_id, include_aliases=True),
        )


@event.listens_for(Session, "before_flush")
def _check_writes(session: Session, *_: object) -> None:
    org_id = session.info.get(_KEY)
    if org_id is None:
        return
    for obj in session.new:
        if isinstance(obj, TenantOwned) and obj.org_id is None:
            obj.org_id = org_id
    for obj in (*session.new, *session.dirty, *session.deleted):
        if _foreign(obj, org_id):
            raise TenancyViolation(f"{type(obj).__name__} written for another org")
