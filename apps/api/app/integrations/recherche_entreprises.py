"""Client for the open "Recherche d'entreprises" API (data.gouv.fr).

Checked on a real reply (2026-11-08, docs/07 §3): the fixture keeps its structure, with
fictitious values. ``adresse`` already holds the postal code and the town, so the street is
rebuilt from its parts; secondary establishments have no ``departement`` (it comes from the
postal code); the legal name is ``nom_raison_sociale`` (``nom_complet`` adds the acronym);
a manager may be listed twice (« DUPONT » and « DUPONT (DUPONT) »).
"""

import logging
import re
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.domain.places import department_of

logger = logging.getLogger("pilao.recherche_entreprises")

CACHE_TTL_SECONDS = 24 * 3600
CACHE_MAX_ENTRIES = 10_000
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


def _dicts(value: Any) -> list[dict[str, Any]]:
    """Objects of a JSON list (or a single object); anything else is ignored (unverified shape)."""
    items = value if isinstance(value, list) else [value]
    return [v for v in items if isinstance(v, dict)]


def _street(etab: dict[str, Any]) -> str | None:
    """« 1 B RUE DE LA PAIX, BATIMENT A »: the street without postal code and town."""
    parts = [_clean(etab.get(k)) for k in ("numero_voie", "indice_repetition", "type_voie")]
    street = " ".join(filter(None, [*parts, _clean(etab.get("libelle_voie"))]))
    if street:
        extra = _clean(etab.get("complement_adresse"))
        return f"{street}, {extra}" if extra else street
    full = _clean(etab.get("adresse"))  # fallback: drop the « 42000 SAINT-ETIENNE » tail
    postal = _clean(etab.get("code_postal"))
    if full and postal and postal in full:
        return full[: full.index(postal)].strip(" ,") or None
    return full


def parse_company(payload: dict[str, Any], siret: str) -> CompanyInfo | None:
    """Pick the establishment matching ``siret`` out of a /search response, if any."""
    for result in _dicts(payload.get("results")):
        etabs = [*_dicts(result.get("siege")), *_dicts(result.get("matching_etablissements"))]
        etab = next((e for e in etabs if e.get("siret") == siret), None)
        if etab is None:
            continue
        managers: dict[str, str] = {}  # one per person: « ABD RAOUF » = « ABD-RAOUF »
        for d in _dicts(result.get("dirigeants")):
            if d.get("type_dirigeant", "personne physique") != "personne physique":
                continue
            last = re.sub(r"\s*\(.*?\)", "", _clean(d.get("nom")) or "").strip()
            name = " ".join(filter(None, [_clean(d.get("prenoms")), last or None]))
            if name:
                managers.setdefault(re.sub(r"[\s\-]", "", name.upper()), name)
        state = _clean(etab.get("etat_administratif"))
        postal = _clean(etab.get("code_postal"))
        return CompanyInfo(
            siren=str(result.get("siren") or siret[:9]),
            siret=siret,
            name=_clean(result.get("nom_raison_sociale"))
            or _clean(result.get("nom_complet"))
            or "",
            legal_form=_clean(result.get("nature_juridique")),
            naf_code=_clean(etab.get("activite_principale"))
            or _clean(result.get("activite_principale")),
            address_line=_street(etab),
            postal_code=postal,
            city=_clean(etab.get("libelle_commune")),
            department=_clean(etab.get("departement")) or department_of(postal),
            headcount_range=_clean(etab.get("tranche_effectif_salarie"))
            or _clean(result.get("tranche_effectif_salarie")),
            is_active=None if state is None else state == "A",
            managers=tuple(managers.values()),
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
        self._lock = threading.Lock()

    def lookup_siret(self, siret: str) -> CompanyInfo | None:
        if not re.fullmatch(r"\d{14}", siret):
            raise ValueError("siret must be 14 digits")
        now = time.monotonic()
        hit = self._cache.get(siret)
        if hit and hit[0] > now:
            return hit[1]
        try:
            info = parse_company(self._get({"q": siret, "page": 1, "per_page": 1}), siret)
        except CompanyLookupUnavailable:
            raise
        except Exception as exc:  # unexpected response shape: callers only handle "unavailable"
            logger.warning("recherche-entreprises unparseable response: %r", exc)
            raise CompanyLookupUnavailable("unparseable response") from exc
        with self._lock:  # requests run in a thread pool
            if len(self._cache) >= CACHE_MAX_ENTRIES:  # public endpoint: keep memory bounded
                self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
                while len(self._cache) >= CACHE_MAX_ENTRIES:
                    self._cache.pop(next(iter(self._cache)))
            self._cache[siret] = (now + CACHE_TTL_SECONDS, info)
        return info

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                res = self._http.get(f"{self._base}/search", params=params)
                if res.status_code == 429 or res.status_code >= 500:
                    delay = _retry_after(res.headers.get("retry-after"), 2**attempt * 0.5)
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
            except httpx.HTTPStatusError as exc:  # 3xx/4xx other than 429: do not retry
                raise CompanyLookupUnavailable(f"HTTP {exc.response.status_code}") from exc
            except (httpx.HTTPError, ValueError) as exc:  # transport, decoding, bad JSON…
                last = exc
                logger.warning("recherche-entreprises error: %s", exc)
                if attempt < MAX_ATTEMPTS - 1:
                    self._sleep(2**attempt * 0.5)
        raise CompanyLookupUnavailable(str(last)) from last


def _retry_after(header: str | None, default: float) -> float:
    """Seconds from a ``Retry-After`` header (delta form only; HTTP-date or junk → default)."""
    try:
        delay = float(header) if header is not None else default
    except ValueError:
        return default
    return delay if delay >= 0 else default


@lru_cache
def get_company_directory() -> CompanyDirectory:
    return RechercheEntreprisesClient()
