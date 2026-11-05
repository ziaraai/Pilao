from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.limits import BodySizeLimitMiddleware
from app.routers import (
    auth,
    bids,
    companies,
    documents,
    files,
    knowledge,
    memoir,
    profile,
    vault,
)
from app.storage.antivirus import get_scanner


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_scanner()  # production without CLAMAV_HOST: refuse to start (ADR-011), fail closed
    yield


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


@app.get("/health")
def health() -> dict[str, str]:
    get_settings()
    return {"status": "ok"}
