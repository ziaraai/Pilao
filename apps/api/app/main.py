from fastapi import FastAPI

from app.core.config import get_settings

app = FastAPI(title="Pilao API")


@app.get("/health")
def health() -> dict[str, str]:
    get_settings()
    return {"status": "ok"}
