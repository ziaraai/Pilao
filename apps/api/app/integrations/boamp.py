"""BOAMP reader: the « boamp » dataset of the DILA on Opendatasoft (Explore API v2.1).

**To check from the server** (docs/07 §1): the development sessions could not reach the host
(their egress opens the connection, the server never answers the TLS handshake), so the
field names below come from the dataset's documentation and are not yet verified on a real
reply. Hence:
* the import of BOAMP stays off (``BOAMP_IMPORT_ENABLED=false``) until checked;
* ``python -m app.cli import-tenders --source boamp --essai`` prints, without saving
  anything, the dataset's real field list, the keys of a real record and 3 notices as Pilao
  reads them: what is needed to correct this module, then switch the import on;
* the conversion is tolerant: a missing or renamed field gives an empty value, never an
  error, and a notice without title or identifier is skipped.

Expected fields: ``idweb`` (notice number, « 26-123456 »), ``objet``, ``nomacheteur``,
``dateparution``, ``datelimitereponse``, ``code_departement`` (list), ``type_marche``,
``nature`` / ``nature_libelle`` (call for tenders, correction, award), ``procedure_libelle``,
``url_avis``, ``annonce_lie`` / ``annonces_anterieures`` (the notice a correction modifies)
and ``donnees`` (the whole notice, JSON in a string: CPV codes, lots, amounts).
"""

import json
import logging
import re
import time
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.tenders import NoticeType, TenderIn

logger = logging.getLogger("pilao.boamp")
PARIS = ZoneInfo("Europe/Paris")
DATASET = "boamp"
PAGE_SIZE = 100  # Opendatasoft maximum for /records
MAX_OFFSET = 10_000  # /records refuses offset + limit beyond this
MAX_ATTEMPTS = 4
CPV_NEAR_KEY = re.compile(
    r"(?:cpv|classprincipale|classsupplementaire|itemclassificationcode)[^0-9]{0,120}?(\d{8})",
    re.IGNORECASE,
)


class BoampUnavailable(Exception):
    """BOAMP did not answer usably (network, 5xx, quota, unexpected reply)."""


class BoampClient:
    def __init__(
        self,
        base_url: str | None = None,
        http: httpx.Client | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self._base = (base_url or get_settings().boamp_api_url).rstrip("/")
        self._http = http or httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))
        self._sleep = sleep

    def fields(self) -> list[str]:
        """The dataset's field names, as the API describes them (server check)."""
        data = self._get(f"/catalog/datasets/{DATASET}", {})
        return [str(f.get("name")) for f in data.get("fields", []) if isinstance(f, dict)]

    def records(
        self, since: date, limit: int | None = None, until: date | None = None
    ) -> Iterator[dict[str, Any]]:
        """Notices published from ``since`` to ``until`` (today), one day at a time: BOAMP
        publishes more than a thousand a day, and /records stops at 10 000 per query."""
        day, last, seen = since, until or date.today(), 0
        while day <= last:
            for record in self._day(day, None if limit is None else limit - seen):
                yield record
                seen += 1
                if limit is not None and seen >= limit:
                    return
            day += timedelta(days=1)

    def _day(self, day: date, limit: int | None) -> Iterator[dict[str, Any]]:
        offset = 0
        while offset < MAX_OFFSET:
            size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - offset)
            if size <= 0:
                return
            page = self._get(
                f"/catalog/datasets/{DATASET}/records",
                {
                    "where": f"dateparution = date'{day.isoformat()}'",
                    "order_by": "idweb asc",
                    "limit": size,
                    "offset": offset,
                },
            )
            results = page.get("results")
            if not isinstance(results, list):
                raise BoampUnavailable("reply without results")
            yield from (r for r in results if isinstance(r, dict))
            if len(results) < size:
                return
            offset += size
        logger.warning("BOAMP: more than %d notices on %s, the rest is not read", MAX_OFFSET, day)

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                res = self._http.get(f"{self._base}{path}", params=params)
                if res.status_code == 429 or res.status_code >= 500:
                    last = BoampUnavailable(f"HTTP {res.status_code}")
                    logger.warning("BOAMP %s, attempt %d", res.status_code, attempt + 1)
                    if attempt < MAX_ATTEMPTS - 1:
                        self._sleep(min(2**attempt * 2, 30))
                    continue
                if res.status_code >= 400:
                    raise BoampUnavailable(f"HTTP {res.status_code}: {res.text[:300]}")
                data = res.json()
                if not isinstance(data, dict):
                    raise BoampUnavailable("reply is not an object")
                return data
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                logger.warning("BOAMP error: %s", exc)
                if attempt < MAX_ATTEMPTS - 1:
                    self._sleep(min(2**attempt * 2, 30))
        raise BoampUnavailable(str(last)) from last


# ---------- conversion ------------------------------------------------------------------


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _str(value: Any) -> str | None:
    first = _list(value)[0] if _list(value) else None
    return str(first).strip() or None if first is not None else None


def _when(value: Any, end_of_day: bool = False) -> datetime | None:
    raw = _str(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)  # Python 3.11+ reads a final « Z »
    except ValueError:
        return None
    if len(raw) == 10 and end_of_day:  # a date alone: the whole day counts
        parsed = parsed.replace(hour=23, minute=59)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=PARIS)


def _donnees(record: dict[str, Any]) -> str:
    raw = record.get("donnees")
    if isinstance(raw, dict | list):
        return json.dumps(raw, ensure_ascii=False)
    return str(raw) if raw else ""


def _notice_type(record: dict[str, Any]) -> NoticeType:
    nature = " ".join(
        str(x)
        for k in ("nature", "nature_libelle", "nature_categorise")
        for x in _list(record.get(k))
    ).lower()
    if "rectif" in nature or "modif" in nature:
        return "correction"
    if "attribution" in nature or "résultat" in nature or "resultat" in nature:
        return "award"
    return "contract_notice"


def _nature(record: dict[str, Any]) -> Literal["services", "works", "supplies"] | None:
    words = " ".join(str(x) for x in _list(record.get("type_marche"))).lower()
    if "service" in words:
        return "services"
    if "travaux" in words:
        return "works"
    if "fourniture" in words:
        return "supplies"
    return None


def to_tender(record: dict[str, Any]) -> TenderIn | None:
    idweb = _str(record.get("idweb")) or _str(record.get("id"))
    title = _str(record.get("objet"))
    if not idweb or not title:
        return None
    kind = _notice_type(record)
    donnees = _donnees(record)
    corrects = _str(record.get("annonce_lie")) or _str(record.get("annonces_anterieures"))
    # where the work is done first, else the buyer's department
    places = _list(record.get("code_departement_prestation")) or _list(
        record.get("code_departement")
    )
    departments = [
        d for d in (str(x).strip().upper() for x in places) if re.fullmatch(r"\d{2,3}|2[AB]", d)
    ]
    nature = _nature(record)
    url = _str(record.get("url_avis")) or f"https://www.boamp.fr/pages/avis/?q=idweb:{idweb}"
    return TenderIn(
        source="boamp",
        source_id=idweb,
        notice_type=kind if kind != "correction" or corrects else "contract_notice",
        corrects=corrects if kind == "correction" else None,
        title=title[:2000],
        buyer_name=_str(record.get("nomacheteur")),
        procedure=_str(record.get("procedure_libelle")),
        contract_nature=nature,
        cpv_codes=list(dict.fromkeys(CPV_NEAR_KEY.findall(donnees))),
        departments=list(dict.fromkeys(departments)),
        published_at=_when(record.get("dateparution")),
        deadline_at=_when(record.get("datelimitereponse"), end_of_day=True),
        notice_url=url,
        raw={"idweb": idweb, "nature": record.get("nature"), "famille": record.get("famille")},
    )


class BoampReader:
    """The BOAMP source for ``services/tender_import.py``. BOAMP cannot be searched by CPV
    code (they are inside ``donnees``): every notice of the period is read, and the
    pre-filter of each company does the sorting."""

    def __init__(self, client: BoampClient | None = None) -> None:
        self._client = client or BoampClient()

    def fetch(
        self, cpv_codes: list[str], since: date, limit: int | None = None
    ) -> Iterator[TenderIn | None]:
        for record in self._client.records(since, limit):
            try:
                yield to_tender(record)
            except ValidationError as exc:
                logger.warning("BOAMP notice %s not converted: %s", record.get("idweb"), exc)
                yield None

    def probe(self, since: date) -> dict[str, Any]:
        """For ``--essai``: the real field list and the keys of one real record."""
        first = next(iter(self._client.records(since, 1)), {})
        return {
            "fields": self._client.fields(),
            "record": {k: str(v)[:120] for k, v in first.items() if k != "donnees"},
            "donnees": _donnees(first)[:600],
        }
