"""Routes of the platform administration, all under ``/admin`` (ADR-040)."""

from fastapi import APIRouter

from app.routers.admin import auth, supervision

router = APIRouter()
router.include_router(auth.router)
router.include_router(supervision.router)
