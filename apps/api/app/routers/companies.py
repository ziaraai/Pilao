import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.core.ratelimit import SlidingWindowLimiter
from app.integrations.recherche_entreprises import (
    CompanyDirectory,
    CompanyInfo,
    CompanyLookupUnavailable,
    get_company_directory,
)
from app.schemas.auth import luhn_ok

logger = logging.getLogger("pilao.companies")
router = APIRouter(prefix="/companies", tags=["companies"])
_limiter = SlidingWindowLimiter(max_calls=20, window_seconds=60)


class CompanyInfoOut(BaseModel):
    siren: str
    siret: str
    name: str
    legal_form: str | None
    naf_code: str | None
    address_line: str | None
    postal_code: str | None
    city: str | None
    department: str | None
    headcount_range: str | None
    is_active: bool | None


class LookupOut(BaseModel):
    """``available=False`` means the registry could not be queried: let the user type it in."""

    available: bool
    found: bool
    company: CompanyInfoOut | None = None


@router.get("/lookup")
def lookup(
    siret: Annotated[str, Query(pattern=r"^\d{14}$")],
    request: Request,
    directory: Annotated[CompanyDirectory, Depends(get_company_directory)],
) -> LookupOut:
    """Pre-fill company identity from a SIRET (US-1.1). Public: used before the account exists."""
    _limiter.check(request.client.host if request.client else "unknown")
    if not luhn_ok(siret) and not siret.startswith("356000000"):
        return LookupOut(available=True, found=False)
    try:
        info: CompanyInfo | None = directory.lookup_siret(siret)
    except CompanyLookupUnavailable:
        return LookupOut(available=False, found=False)
    if info is None:
        return LookupOut(available=True, found=False)
    return LookupOut(
        available=True,
        found=True,
        company=CompanyInfoOut(**{k: getattr(info, k) for k in CompanyInfoOut.model_fields}),
    )
