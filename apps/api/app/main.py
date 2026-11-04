from fastapi import FastAPI

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.core.limits import BodySizeLimitMiddleware
from app.routers import auth, companies, files, profile

app = FastAPI(title="Pilao API")
install_error_handlers(app)
app.add_middleware(BodySizeLimitMiddleware)
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(profile.router)
app.include_router(files.router)


@app.get("/health")
def health() -> dict[str, str]:
    get_settings()
    return {"status": "ok"}
