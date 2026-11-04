"""Client for the open "Recherche d'entreprises" API (data.gouv.fr).

Status: written from the documented fields (docs/07-integrations-api.md §3). The session that
wrote it could not reach the host, so the real response shape is still **to verify**: the
parser is deliberately tolerant (every field optional) and the test fixture is hand-written.
"""

import logging
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger("pilao.recherche_entreprises")

CACHE_TTL_SECONDS = 24 * 3600
MAX_ATTEMPTS = 3


class CompanyLookupUnavailable(Exception):
    """The external API failed (network, 5xx, quota). Callers must fall back to manual entry."""


@dataclass(frozen=True)
class CompanyInfo:
    siren: str
    siret: str
    name: str
    legal_form: str | None = None  # code nature_juridique (INSEE)
    naf_code: str | None = None
    address_line: str | None = None
    postal_code: str | None = None
    city: str | None = None
    department: str | None = None
    headcount_range: str | None = None  # code tranche d'effectif INSEE
    is_active: bool | None = None
    managers: tuple[str, ...] = ()


class CompanyDirectory(Protocol):
    def lookup_siret(self, siret: str) -> CompanyInfo | None: ...


def _clean(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def parse_company(payload: dict[str, Any], siret: str) -> CompanyInfo | None:
    """Pick the establishment matching ``siret`` out of a /search response, if any."""
    for result in payload.get("results") or []:
        etabs = [result.get("siege") or {}, *(result.get("matching_etablissements") or [])]
        etab = next((e for e in etabs if e.get("siret") == siret), None)
        if etab is None:
            continue
        managers = tuple(
            " ".join(filter(None, [_clean(d.get("prenoms")), _clean(d.get("nom"))]))
            for d in result.get("dirigeants") or []
            if d.get("type_dirigeant", "personne physique") == "personne physique"
        )
        state = _clean(etab.get("etat_administratif"))
        return CompanyInfo(
            siren=str(result.get("siren") or siret[:9]),
            siret=siret,
            name=_clean(result.get("nom_complet"))
            or _clean(result.get("nom_raison_sociale"))
            or "",
            legal_form=_clean(result.get("nature_juridique")),
            naf_code=_clean(etab.get("activite_principale"))
            or _clean(result.get("activite_principale")),
            address_line=_clean(etab.get("adresse")),
            postal_code=_clean(etab.get("code_postal")),
            city=_clean(etab.get("libelle_commune")),
            department=_clean(etab.get("departement")),
            headcount_range=_clean(etab.get("tranche_effectif_salarie"))
            or _clean(result.get("tranche_effectif_salarie")),
            is_active=None if state is None else state == "A",
            managers=tuple(m for m in managers if m),
        )
    return None


class RechercheEntreprisesClient:
    def __init__(
        self,
        base_url: str | None = None,
        http: httpx.Client | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self._base = (base_url or get_settings().recherche_entreprises_base_url).rstrip("/")
        self._http = http or httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0))
        self._sleep = sleep
        self._cache: dict[str, tuple[float, CompanyInfo | None]] = {}

    def lookup_siret(self, siret: str) -> CompanyInfo | None:
        if not re.fullmatch(r"\d{14}", siret):
            raise ValueError("siret must be 14 digits")
        hit = self._cache.get(siret)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        info = parse_company(self._get({"q": siret, "page": 1, "per_page": 1}), siret)
        self._cache[siret] = (time.monotonic() + CACHE_TTL_SECONDS, info)
        return info

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                res = self._http.get(f"{self._base}/search", params=params)
                if res.status_code == 429 or res.status_code >= 500:
                    delay = float(res.headers.get("retry-after", 2**attempt * 0.5))
                    last = CompanyLookupUnavailable(f"HTTP {res.status_code}")
                    logger.warning(
                        "recherche-entreprises %s, retry in %.1fs", res.status_code, delay
                    )
                    if attempt < MAX_ATTEMPTS - 1:
                        self._sleep(min(delay, 5.0))
                    continue
                res.raise_for_status()
                data = res.json()
                return data if isinstance(data, dict) else {}
            except (httpx.TransportError, ValueError) as exc:
                last = exc
                logger.warning("recherche-entreprises error: %s", exc)
                if attempt < MAX_ATTEMPTS - 1:
                    self._sleep(2**attempt * 0.5)
            except httpx.HTTPStatusError as exc:  # 4xx other than 429: do not retry
                raise CompanyLookupUnavailable(f"HTTP {exc.response.status_code}") from exc
        raise CompanyLookupUnavailable(str(last)) from last


@lru_cache
def get_company_directory() -> CompanyDirectory:
    return RechercheEntreprisesClient()
