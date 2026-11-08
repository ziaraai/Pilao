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
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.integrations.boamp_donnees import parse as parse_donnees
from app.schemas.tenders import LotIn, NoticeType, TenderIn

logger = logging.getLogger("pilao.boamp")
PARIS = ZoneInfo("Europe/Paris")
DATASET = "boamp"
PAGE_SIZE = 100  # Opendatasoft maximum for /records
MAX_OFFSET = 10_000  # /records refuses offset + limit beyond this
MAX_ATTEMPTS = 4
LISTING = "idweb,datelimitereponse,nature,nature_libelle"
BY_IDS = 40  # numbers per query (the URL stays short)
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

    def listing(self, day: date) -> Iterator[dict[str, Any]]:
        """The day's notices, light: number, deadline and nature only (no « donnees »)."""
        yield from self._day(day, None, select=LISTING)

    def by_ids(self, ids: list[str]) -> Iterator[dict[str, Any]]:
        """Whole notices, by number, a few dozen per query."""
        safe = [i for i in ids if re.fullmatch(r"[\w-]{1,40}", i)]
        for start in range(0, len(safe), BY_IDS):
            chunk = safe[start : start + BY_IDS]
            page = self._get(
                f"/catalog/datasets/{DATASET}/records",
                {"where": " OR ".join(f'idweb = "{i}"' for i in chunk), "limit": PAGE_SIZE},
            )
            results = page.get("results")
            if not isinstance(results, list):
                raise BoampUnavailable("reply without results")
            yield from (r for r in results if isinstance(r, dict))

    def _day(
        self, day: date, limit: int | None, select: str | None = None
    ) -> Iterator[dict[str, Any]]:
        offset = 0
        while offset < MAX_OFFSET:
            size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - offset)
            if size <= 0:
                return
            params: dict[str, Any] = {
                "where": f"dateparution = date'{day.isoformat()}'",
                "order_by": "idweb asc",
                "limit": size,
                "offset": offset,
            }
            if select:
                params["select"] = select
            page = self._get(f"/catalog/datasets/{DATASET}/records", params)
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


def _closed(row: dict[str, Any], now: datetime) -> bool:
    deadline = _when(row.get("datelimitereponse"), end_of_day=True)
    return deadline is not None and deadline < now


def _donnees(record: dict[str, Any]) -> str:
    raw = record.get("donnees")
    if isinstance(raw, dict | list):
        return json.dumps(raw, ensure_ascii=False)
    return str(raw) if raw else ""


def _department(raw: Any) -> str | None:
    """« 42 », « 2A » as the profiles write them; BOAMP writes Corsica « 20A » / « 20B »."""
    code = str(raw).strip().upper()
    code = {"20A": "2A", "20B": "2B"}.get(code, code)
    if re.fullmatch(r"\d", code):
        code = f"0{code}"
    return code if re.fullmatch(r"\d{2,3}|2[AB]", code) else None


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
    departments = [d for d in (_department(x) for x in places) if d]
    nature = _nature(record)
    url = _str(record.get("url_avis")) or f"https://www.boamp.fr/pages/avis/?q=idweb:{idweb}"
    details = parse_donnees(record.get("donnees"))
    return TenderIn(
        source="boamp",
        source_id=idweb,
        notice_type=kind if kind != "correction" or corrects else "contract_notice",
        corrects=corrects if kind == "correction" else None,
        title=title[:2000],
        description=details.description[:20_000] if details.description else None,
        buyer_name=_str(record.get("nomacheteur")),
        procedure=_str(record.get("procedure_libelle")),
        contract_nature=nature,
        cpv_codes=list(dict.fromkeys(CPV_NEAR_KEY.findall(donnees))),
        departments=list(dict.fromkeys(departments)),
        published_at=_when(record.get("dateparution")),
        deadline_at=_when(record.get("datelimitereponse"), end_of_day=True),
        notice_url=url,
        documents_url=details.documents_url,
        estimated_amount_eur=details.amount_eur,
        lots=[
            LotIn(number=lot.number, title=lot.title, estimated_amount_eur=lot.amount_eur)
            for lot in details.lots
        ],
        raw={"idweb": idweb, "nature": record.get("nature"), "famille": record.get("famille")},
    )


class BoampReader:
    """The BOAMP source for ``services/tender_import.py``. BOAMP cannot be searched by CPV
    code (they are inside ``donnees``) and publishes over a thousand notices a day, each
    20 to 80 KB with ``donnees``. So each day is first listed light (number, deadline,
    nature); then only the notices still open, not yet stored and that are not awards
    (useless to answer, many) are read in full."""

    def __init__(self, client: BoampClient | None = None) -> None:
        self._client = client or BoampClient()

    def fetch(
        self,
        cpv_codes: list[str],
        since: date,
        limit: int | None = None,
        known: Callable[[list[str]], set[str]] | None = None,
        now: datetime | None = None,
    ) -> Iterator[TenderIn | None]:
        moment = now or datetime.now(UTC)
        day, last, seen = since, moment.date(), 0
        while day <= last:
            wanted = [
                idweb
                for row in self._client.listing(day)
                if (idweb := _str(row.get("idweb")))
                and _notice_type(row) != "award"
                and not _closed(row, moment)
            ]
            if known and wanted:
                stored = known(wanted)
                wanted = [i for i in wanted if i not in stored]
            for record in self._client.by_ids(wanted):
                try:
                    yield to_tender(record)
                except ValidationError as exc:
                    logger.warning("BOAMP notice %s not converted: %s", record.get("idweb"), exc)
                    yield None
                seen += 1
                if limit is not None and seen >= limit:
                    return
            day += timedelta(days=1)

    def probe(self, since: date) -> dict[str, Any]:
        """For ``--essai``: the real field list and the keys of one real record."""
        first = next(iter(self._client.records(since, 1)), {})
        return {
            "fields": self._client.fields(),
            "record": {k: str(v)[:120] for k, v in first.items() if k != "donnees"},
            "donnees": _donnees(first)[:600],
        }
