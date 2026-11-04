from collections.abc import Callable, Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Organization
from app.integrations.recherche_entreprises import (
    CompanyInfo,
    CompanyLookupUnavailable,
    get_company_directory,
)
from app.main import app
from tests.api.helpers import register_payload

Factory = Callable[[], TestClient]


class FakeDirectory:
    def __init__(self) -> None:
        self.mode = "found"

    def lookup_siret(self, siret: str) -> CompanyInfo | None:
        if self.mode == "down":
            raise CompanyLookupUnavailable("down")
        if self.mode == "missing":
            return None
        return CompanyInfo(
            siren=siret[:9],
            siret=siret,
            name="NETTOYAGE EXEMPLE",
            legal_form="5710",
            naf_code="81.21Z",
            address_line="1 RUE X",
            postal_code="75002",
            city="PARIS",
            department="75",
            headcount_range="12",
            is_active=True,
        )


@pytest.fixture
def directory(make_client: Factory) -> Iterator[FakeDirectory]:
    from app.routers import companies

    fake = FakeDirectory()
    companies._limiter._hits.clear()  # module-level limiter: isolate each test
    app.dependency_overrides[get_company_directory] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_company_directory, None)
    companies._limiter._hits.clear()


SIRET = register_payload(1)["siret"]


def test_lookup_found(make_client: Factory, directory: FakeDirectory) -> None:
    body = make_client().get(f"/companies/lookup?siret={SIRET}").json()
    assert body["available"] and body["found"]
    assert body["company"]["name"] == "NETTOYAGE EXEMPLE" and body["company"]["city"] == "PARIS"


def test_lookup_not_found_and_invalid_checksum(
    make_client: Factory, directory: FakeDirectory
) -> None:
    directory.mode = "missing"
    c = make_client()
    assert c.get(f"/companies/lookup?siret={SIRET}").json() == {
        "available": True,
        "found": False,
        "company": None,
    }
    directory.mode = "found"  # invalid Luhn is rejected before calling the registry
    assert c.get("/companies/lookup?siret=12345678901234").json()["found"] is False


def test_lookup_registry_down_allows_manual_entry(
    make_client: Factory, directory: FakeDirectory
) -> None:
    directory.mode = "down"
    res = make_client().get(f"/companies/lookup?siret={SIRET}")
    assert res.status_code == 200 and res.json()["available"] is False


def test_lookup_validates_input(make_client: Factory, directory: FakeDirectory) -> None:
    assert make_client().get("/companies/lookup?siret=abc").status_code == 422


def test_lookup_accepts_spaces_like_register(
    make_client: Factory, directory: FakeDirectory
) -> None:
    spaced = f"{SIRET[:3]} {SIRET[3:6]} {SIRET[6:9]} {SIRET[9:]}"
    body = make_client().get("/companies/lookup", params={"siret": spaced}).json()
    assert body["found"] and body["company"]["siret"] == SIRET


def test_lookup_is_rate_limited(make_client: Factory, directory: FakeDirectory) -> None:
    from app.routers import companies

    companies._limiter._hits.clear()
    c = make_client()
    codes = [c.get(f"/companies/lookup?siret={SIRET}").status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429
    companies._limiter._hits.clear()


def test_register_prefills_org_from_registry(
    make_client: Factory, directory: FakeDirectory, db: Session
) -> None:
    assert make_client().post("/auth/register", json=register_payload(1)).status_code == 201
    org = db.scalars(select(Organization)).one()
    assert (org.naf_code, org.postal_code, org.city, org.legal_form) == (
        "81.21Z",
        "75002",
        "PARIS",
        "5710",
    )
    assert org.name == "Entreprise 1"  # the name typed by the user is kept


def test_register_ignores_registry_values_too_long_for_the_schema(
    make_client: Factory, directory: FakeDirectory, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = directory.lookup_siret

    def odd(siret: str) -> CompanyInfo | None:
        info = real(siret)
        assert info is not None
        return replace(info, department="Paris (75)")  # CHAR(3) column

    monkeypatch.setattr(directory, "lookup_siret", odd)
    assert make_client().post("/auth/register", json=register_payload(1)).status_code == 201
    org = db.scalars(select(Organization)).one()
    assert org.department is None and org.city == "PARIS"


def test_register_still_works_when_registry_is_down(
    make_client: Factory, directory: FakeDirectory, db: Session
) -> None:
    directory.mode = "down"
    assert make_client().post("/auth/register", json=register_payload(1)).status_code == 201
    assert db.scalars(select(Organization)).one().naf_code is None
