"""Platform settings from the administration (lot 5, ADR-044): AI models, the OpenRouter key,
the notice imports and the general settings. Every change is journaled; the value in use is
read through ``app.core.runtime``, invalidated after each write."""

import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import llm
from app.ai.openrouter import CatalogueModel, KeyRefused, OpenRouter, OpenRouterUnavailable
from app.core import crypto, runtime
from app.core.admin_deps import AdminContext
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.models import AiCall, PlatformAdmin, PlatformSetting, TenderImport
from app.domain.admin_watch import WatchItem
from app.domain.ai_catalogue import NEEDS_IMAGES, eur_per_million, usable
from app.platform_settings import BY_NAME, GENERAL, IMPORTS, MODEL_LABELS
from app.schemas.admin import (
    ApiKeyOut,
    CatalogueModelOut,
    CreditOut,
    GeneralSettingOut,
    ImportSettingOut,
    LastPassOut,
    ModelSettingOut,
    SettingsOut,
)
from app.services.admin import audit
from app.services.admin import auth as admin_auth
from app.workers.queue import TENDER_JOB_TIMEOUT_SECONDS, JobQueue

logger = logging.getLogger("pilao.admin.settings")
_EMAIL: TypeAdapter[str] = TypeAdapter(EmailStr)

CATALOGUE_TTL_SECONDS = 3600
KEY = runtime.KEY

_cache_lock = threading.Lock()
_cache: tuple[float, list[CatalogueModel]] | None = None


def clear_catalogue_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def cached_catalogue() -> list[CatalogueModel] | None:
    """The catalogue read less than an hour ago, without asking OpenRouter."""
    with _cache_lock:
        if _cache is not None and time.monotonic() - _cache[0] < CATALOGUE_TTL_SECONDS:
            return _cache[1]
    return None


def read_catalogue(client: OpenRouter) -> list[CatalogueModel]:
    """Raises ``OpenRouterUnavailable``."""
    global _cache
    known = cached_catalogue()
    if known is not None:
        return known
    models = client.models()
    with _cache_lock:
        _cache = (time.monotonic(), models)
    return models


def _catalogue_or_503(client: OpenRouter) -> list[CatalogueModel]:
    try:
        return read_catalogue(client)
    except OpenRouterUnavailable:
        raise ApiError(
            503,
            "catalogue_unavailable",
            "Catalogue OpenRouter indisponible, réessayez dans un moment.",
        ) from None


def _task_or_404(task: str) -> str:
    if task not in MODEL_LABELS:
        raise ApiError(404, "unknown_task", "Tâche inconnue.")
    return task


def _usable_for(models: list[CatalogueModel], task: str) -> list[CatalogueModel]:
    found = [m for m in models if usable(m, needs_images=task in NEEDS_IMAGES)]
    return sorted(found, key=lambda m: (m.name.casefold(), m.id))


def catalogue_id(model: str) -> str:
    """The catalogue identifier of a LiteLLM model name (``openrouter/acme/x`` → ``acme/x``)."""
    prefix = get_settings().llm_catalogue_prefix
    return model[len(prefix) :] if prefix and model.startswith(prefix) else model


def catalogue(client: OpenRouter, task: str) -> list[CatalogueModelOut]:
    _task_or_404(task)
    rate = get_settings().usd_eur_rate
    return [
        CatalogueModelOut(
            id=m.id,
            name=m.name,
            price_in_eur=eur_per_million(m.prompt_usd, rate),
            price_out_eur=eur_per_million(m.completion_usd, rate),
            context_length=m.context_length,
        )
        for m in _usable_for(_catalogue_or_503(client), task)
    ]


# ---------- the screen ---------------------------------------------------------------------


def _costs(db: Session, now: datetime) -> dict[str, tuple[float, int]]:
    rows = db.execute(
        select(AiCall.task, func.coalesce(func.sum(AiCall.cost_eur), 0), func.count())
        .where(AiCall.created_at >= now - timedelta(days=30))
        .group_by(AiCall.task)
    )
    return {task: (float(cost), int(n)) for task, cost, n in rows}


def _updated_at(name: str) -> datetime | None:
    found = runtime.snapshot().updated.get(name)
    return found[0] if found else None


def model_out(
    task: str, by_id: dict[str, CatalogueModel] | None, costs: dict[str, tuple[float, int]]
) -> ModelSettingOut:
    name = f"model.{task}"
    model = runtime.model_for_task(task)
    entry = by_id.get(catalogue_id(model)) if by_id is not None and model else None
    rate = get_settings().usd_eur_rate
    cost, calls = costs.get(task, (0.0, 0))
    return ModelSettingOut(
        task=task,
        label=MODEL_LABELS[task],
        model=model,
        model_name=entry.name if entry else None,
        source=runtime.source(name),
        server_model=str(BY_NAME[name].server(get_settings()) or ""),
        price_in_eur=eur_per_million(entry.prompt_usd, rate) if entry else None,
        price_out_eur=eur_per_million(entry.completion_usd, rate) if entry else None,
        in_catalogue=None if by_id is None or not model else entry is not None,
        cost_30d_eur=round(cost, 4),
        calls_30d=calls,
        updated_at=_updated_at(name),
    )


def api_key_out(client: OpenRouter) -> ApiKeyOut:
    snap = runtime.snapshot()
    server = get_settings().openrouter_api_key
    if snap.key:
        source, last4 = "admin", snap.key_last4
    elif server:
        source, last4 = "server", server[-4:]
    else:
        source, last4 = "none", None
    credit = None
    key = runtime.api_key()
    if key:
        try:
            c = client.credit(key)
            credit = CreditOut(total_usd=c.total_usd, used_usd=c.used_usd)
        except (OpenRouterUnavailable, KeyRefused):
            credit = None  # « Crédit indisponible »
    return ApiKeyOut(
        source=source,
        last4=last4,
        updated_at=_updated_at(KEY) if source == "admin" else None,
        unreadable=snap.key_unreadable,
        server_key=bool(server),
        credit=credit,
    )


def imports_out(db: Session) -> list[ImportSettingOut]:
    out = []
    for source, name in IMPORTS.items():
        last = db.scalars(
            select(TenderImport)
            .where(TenderImport.source == source)
            .order_by(TenderImport.created_at.desc())
            .limit(1)
        ).first()
        out.append(
            ImportSettingOut(
                source=source,
                label=BY_NAME[name].label,
                enabled=bool(runtime.effective(name)),
                origin=runtime.source(name),
                last=(
                    LastPassOut(
                        started_at=last.created_at,
                        status=last.status,
                        created=last.created,
                        updated=last.updated,
                        error=last.error,
                    )
                    if last
                    else None
                ),
            )
        )
    return out


def general_out(name: str) -> GeneralSettingOut:
    d = BY_NAME[name]
    return GeneralSettingOut(
        name=name,
        label=d.label,
        kind=d.kind,
        value=runtime.effective(name),
        server_value=d.server(get_settings()),
        source=runtime.source(name),
    )


def state(db: Session, client: OpenRouter) -> SettingsOut:
    try:
        by_id: dict[str, CatalogueModel] | None = {m.id: m for m in read_catalogue(client)}
    except OpenRouterUnavailable:
        by_id = None  # prices and « retiré du catalogue » unknown, the rest is shown
    costs = _costs(db, datetime.now(UTC))
    return SettingsOut(
        models=[model_out(task, by_id, costs) for task in MODEL_LABELS],
        embedding_model=get_settings().embedding_model,
        api_key=api_key_out(client),
        imports=imports_out(db),
        general=[general_out(name) for name in GENERAL],
    )


# ---------- writes -------------------------------------------------------------------------


def _store(
    db: Session,
    name: str,
    admin: PlatformAdmin,
    *,
    value: Any = None,
    secret: str | None = None,
    last4: str | None = None,
) -> None:
    row = db.get(PlatformSetting, name)
    if row is None:
        row = PlatformSetting(key=name)
        db.add(row)
    row.value, row.secret, row.secret_last4 = value, secret, last4
    row.updated_at, row.updated_by = datetime.now(UTC), admin.id


def _done(db: Session) -> None:
    db.commit()
    runtime.invalidate()  # this process sees it at once; the others within 30 seconds


def set_model(
    db: Session, admin: PlatformAdmin, client: OpenRouter, task: str, model_id: str, ip: str | None
) -> ModelSettingOut:
    _task_or_404(task)
    models = _catalogue_or_503(client)
    entry = next((m for m in _usable_for(models, task) if m.id == model_id), None)
    if entry is None:
        raise ApiError(422, "model_unfit", "Ce modèle ne convient pas à cette tâche.")
    model = f"{get_settings().llm_catalogue_prefix}{entry.id}"
    try:
        llm.probe(db, model)
    except llm.LlmError as exc:
        raise ApiError(
            422, "model_trial_failed", f"Le modèle n'a pas répondu correctement : {exc}."
        ) from None
    name = f"model.{task}"
    before = runtime.model_for_task(task)
    _store(db, name, admin, value=model)
    meta = {"setting": name, "label": MODEL_LABELS[task], "from": before, "to": model}
    audit.record(db, "setting_changed", admin=admin, ip=ip, meta=meta)
    _done(db)
    return model_out(task, {m.id: m for m in models}, _costs(db, datetime.now(UTC)))


def reset(db: Session, admin: PlatformAdmin, name: str, ip: str | None) -> None:
    """Back to the server's value; refused when the server has none for a model."""
    d = BY_NAME[name]
    row = db.get(PlatformSetting, name)
    if row is None:
        return  # already the server's value
    server = d.server(get_settings())
    if d.kind == "model" and not server:
        raise ApiError(409, "no_server_value", "Le serveur n'a pas de valeur pour ce réglage.")
    before = runtime.effective(name)
    db.delete(row)
    meta = {"setting": name, "label": d.label, "from": before, "to": server}
    audit.record(db, "setting_reset", admin=admin, ip=ip, meta=meta)
    _done(db)


def reset_model(db: Session, admin: PlatformAdmin, task: str, ip: str | None) -> None:
    reset(db, admin, f"model.{_task_or_404(task)}", ip)


def set_api_key(
    db: Session,
    ctx: AdminContext,
    client: OpenRouter,
    key: str,
    code: str,
    ip: str | None,
) -> ApiKeyOut:
    """Checked with OpenRouter, then the authenticator code asked again (whoever sets the key
    receives every prompt of every company), then stored encrypted."""
    admin = ctx.admin
    try:
        client.check_key(key)
    except KeyRefused:
        raise ApiError(422, "key_refused", "Clé refusée par OpenRouter.") from None
    except OpenRouterUnavailable:
        raise ApiError(
            503,
            "openrouter_unavailable",
            "OpenRouter ne répond pas : la clé n'est pas vérifiée, rien n'est changé.",
        ) from None
    admin_auth.confirm_code(db, admin, ctx.session, code, ip)  # 400 « Code incorrect. »
    last4 = key[-4:]
    _store(db, KEY, admin, secret=crypto.encrypt(key, KEY), last4=last4)
    audit.record(db, "api_key_replaced", admin=admin, ip=ip, meta={"last4": last4})
    _done(db)
    return api_key_out(client)


def reset_api_key(db: Session, admin: PlatformAdmin, ip: str | None) -> None:
    row = db.get(PlatformSetting, KEY)
    if row is None:
        return
    if not get_settings().openrouter_api_key:
        raise ApiError(
            409,
            "no_server_key",
            "Le serveur n'a pas de clé : remplacez la clé plutôt que de la retirer.",
        )
    db.delete(row)
    audit.record(db, "api_key_reset", admin=admin, ip=ip, meta={})
    _done(db)


# ---------- imports and general settings (task 5) ------------------------------------------


def _source_or_404(source: str) -> str:
    if source not in IMPORTS:
        raise ApiError(404, "unknown_source", "Source inconnue.")
    return IMPORTS[source]


def _general_or_404(name: str) -> str:
    if name not in GENERAL:
        raise ApiError(404, "unknown_setting", "Réglage inconnu.")
    return name


def _import_out(db: Session, source: str) -> ImportSettingOut:
    return next(i for i in imports_out(db) if i.source == source)


def set_import(
    db: Session, admin: PlatformAdmin, source: str, enabled: bool, ip: str | None
) -> ImportSettingOut:
    name = _source_or_404(source)
    before = bool(runtime.effective(name))
    _store(db, name, admin, value=enabled)
    meta = {"setting": name, "label": BY_NAME[name].label, "from": before, "to": enabled}
    audit.record(db, "setting_changed", admin=admin, ip=ip, meta=meta)
    _done(db)
    return _import_out(db, source)


def reset_import(db: Session, admin: PlatformAdmin, source: str, ip: str | None) -> None:
    reset(db, admin, _source_or_404(source), ip)


def start_import(
    db: Session, admin: PlatformAdmin, queue: JobQueue, source: str, ip: str | None
) -> None:
    """« Importer maintenant »: refused when the source is off, or when a pass of it started
    less than ``2 × TENDER_JOB_TIMEOUT_SECONDS`` ago and still runs (an older one is dead)."""
    name = _source_or_404(source)
    if not runtime.effective(name):
        raise ApiError(409, "import_off", f"Activez d'abord l'import {source.upper()}.")
    alive = datetime.now(UTC) - timedelta(seconds=2 * TENDER_JOB_TIMEOUT_SECONDS)
    running = db.scalar(
        select(TenderImport.id).where(
            TenderImport.source == source,
            TenderImport.status == "running",
            TenderImport.created_at > alive,
        )
    )
    if running is not None:
        raise ApiError(409, "import_running", "Un passage est déjà en cours.")
    try:
        queue.enqueue_import_source(source)
    except Exception:
        logger.exception("could not enqueue the %s import", source)
        raise ApiError(503, "queue_unavailable", "File d'attente indisponible.") from None
    audit.record(db, "import_started", admin=admin, ip=ip, meta={"source": source})
    db.commit()


def _general_value(name: str, value: Any) -> int | str:
    d = BY_NAME[name]
    if d.kind == "int":
        low, high = d.minimum or 0, d.maximum or 0
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            bounds = f"{low} à {high:,}".replace(",", " ")
            raise ApiError(422, "invalid_value", f"Un nombre entier de {bounds}.")
        return value
    text = str(value if value is not None else "").strip()
    if text:
        try:
            _EMAIL.validate_python(text)
        except ValidationError:
            raise ApiError(422, "invalid_value", "Adresse e-mail invalide.") from None
    return text  # empty: « aucune »


def set_general(
    db: Session, admin: PlatformAdmin, name: str, value: Any, ip: str | None
) -> GeneralSettingOut:
    _general_or_404(name)
    clean = _general_value(name, value)
    before = runtime.effective(name)
    _store(db, name, admin, value=clean)
    meta = {"setting": name, "label": BY_NAME[name].label, "from": before, "to": clean}
    audit.record(db, "setting_changed", admin=admin, ip=ip, meta=meta)
    _done(db)
    return general_out(name)


def reset_general(db: Session, admin: PlatformAdmin, name: str, ip: str | None) -> None:
    reset(db, admin, _general_or_404(name), ip)


# ---------- « À surveiller » --------------------------------------------------------------


def known_catalogue_ids(client: OpenRouter) -> set[str] | None:
    """The catalogue's identifiers for the overview: cached, else read within 5 seconds;
    ``None`` when OpenRouter does not answer (no line about the models then)."""
    known = cached_catalogue()
    if known is None:
        try:
            known = client.models(timeout=5)
        except OpenRouterUnavailable:
            return None
        with _cache_lock:
            global _cache
            _cache = (time.monotonic(), known)
    return {m.id for m in known}


def watch_alerts(catalogue_ids: set[str] | None) -> list[WatchItem]:
    alerts = []
    if runtime.snapshot().key_unreadable:
        title = "La clé OpenRouter enregistrée est illisible"
        alerts.append(WatchItem("red", "settings", title, None, None, None))
    if catalogue_ids is not None:
        for task, label in MODEL_LABELS.items():
            model = runtime.model_for_task(task)
            if model and catalogue_id(model) not in catalogue_ids:
                title = f"{label} : modèle retiré du catalogue OpenRouter"
                alerts.append(WatchItem("amber", "settings", title, None, None, None))
    return alerts
