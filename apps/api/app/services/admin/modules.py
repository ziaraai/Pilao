"""A company's modules, from the administration (lot 3, spec §3.1 and §5.4)."""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import Organization
from app.modules import BY_KEY, MODULES, active_modules
from app.schemas.admin import ModuleOut
from app.services import profile as profile_svc
from app.services.admin import audit
from app.services.admin.context import AdminOrgContext
from app.workers.queue import JobQueue

logger = logging.getLogger("pilao.admin.modules")


def set_module(
    ctx: AdminOrgContext, key: str, enabled: bool, queue: JobQueue, ip: str | None
) -> list[str]:
    """Turn one module on or off for the company; nothing of its data is touched.

    Returns the company's active modules. Only a change is written to the journal; turning the
    watch on searches the open notices for the company again, as a reactivation does."""
    module = BY_KEY.get(key)
    if module is None:
        raise ApiError(404, "unknown_module", "Module inconnu.")
    ctx.db.refresh(ctx.org, with_for_update=True)  # two clicks at once: one after the other
    current = active_modules(ctx.org)
    if (key in current) == enabled:
        return current
    wanted = {*current, key} if enabled else set(current) - {key}
    unknown = [k for k in ctx.org.modules if k not in BY_KEY]  # ignored, never erased
    ctx.org.modules = [m.key for m in MODULES if m.key in wanted] + unknown
    if key == "veille":  # the profile asks for the watch settings only with « Veille »
        profile_svc.refresh_completeness(ctx.db, ctx.org)
    action = "module_enabled" if enabled else "module_disabled"
    meta = {"module": module.key, "name": module.name}
    audit.record(ctx.db, action, admin=ctx.admin, org_id=ctx.org.id, ip=ip, meta=meta)
    ctx.db.commit()
    if enabled and key == "veille":
        try:
            queue.enqueue_rematch_org(ctx.org.id)
        except Exception:  # enabled all the same; the next notice import matches it again
            logger.exception("watch enabled for %s: could not queue the search", ctx.org.id)
    return active_modules(ctx.org)


def catalog(db: Session) -> list[ModuleOut]:
    """The registry, with the number of companies that have each module."""
    return [
        ModuleOut(
            key=m.key,
            name=m.name,
            description=m.description,
            contents=list(m.contents),
            nav=list(m.nav),
            organizations=db.scalar(
                select(func.count()).where(Organization.modules.contains([m.key]))
            )
            or 0,
        )
        for m in MODULES
    ]
