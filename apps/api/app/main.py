from fastapi import FastAPI

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.routers import auth, companies

app = FastAPI(title="Pilao API")
install_error_handlers(app)
app.include_router(auth.router)
app.include_router(companies.router)


@app.get("/health")
def health() -> dict[str, str]:
    get_settings()
    return {"status": "ok"}
