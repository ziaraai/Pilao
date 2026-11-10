from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.limits import BodySizeLimitMiddleware
from app.core.logging import configure_logging
from app.db.session import get_sessionmaker
from app.routers import (
    admin,
    auth,
    bids,
    companies,
    dashboard,
    documents,
    feedback,
    files,
    knowledge,
    members,
    memoir,
    organization,
    profile,
    tenders,
    vault,
)
from app.storage.antivirus import get_scanner


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    problems = get_settings().production_problems()
    if problems:  # fail closed: never serve with development settings (ADR-025)
        raise RuntimeError("Configuration de production incomplète : " + " ".join(problems))
    get_scanner()  # production without CLAMAV_HOST: refuse to start (ADR-011), fail closed
    yield


configure_logging()
app = FastAPI(title="Pilao API", lifespan=lifespan)
install_error_handlers(app)
app.add_middleware(BodySizeLimitMiddleware)
# The web app (APP_BASE_URL) calls the API with the session cookie: only that origin is allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().app_base_url],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(profile.router)
app.include_router(files.router)
app.include_router(knowledge.router)
app.include_router(vault.router)
app.include_router(bids.router)
app.include_router(memoir.router)
app.include_router(documents.router)
app.include_router(tenders.router)
app.include_router(dashboard.router)
app.include_router(organization.router)
app.include_router(members.router)
app.include_router(feedback.router)
app.include_router(admin.router)


@app.get("/health")
def health() -> dict[str, str]:
    get_settings()
    return {"status": "ok"}


@app.get("/ready")
def ready() -> JSONResponse:
    """For the load balancer: the API answers only when its database and Redis answer."""
    checks: dict[str, str] = {}
    try:
        with get_sessionmaker()() as db:
            db.execute(text("select 1"))
        checks["database"] = "ok"
    except SQLAlchemyError:
        checks["database"] = "unavailable"
    try:
        Redis.from_url(get_settings().redis_url, socket_timeout=2).ping()
        checks["redis"] = "ok"
    except RedisError:
        checks["redis"] = "unavailable"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ok" if ok else "unavailable", **checks}, 200 if ok else 503)
