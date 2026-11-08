"""TED (Tenders Electronic Daily) reader: the Search API v3, converted to ``TenderIn``.

Verified on real calls (2026-11-08, docs/07 §2):
* ``POST {TED_API_URL}/v3/notices/search``, no key; an unknown field name is refused with the
  list of every supported field.
* ``classification-cpv IN (90910000)`` is hierarchical: it also returns 90911200, 90911300…
* pages of at most 250 notices; ``paginationMode: ITERATION`` follows ``iterationNextToken``.
* a procedure keeps its ``procedure-identifier`` across its notices: the contract notice,
  then each change notice (``change-notice-version-identifier`` = original id + version),
  each a complete notice. One Pilao notice per procedure: ``source_id`` is that identifier.
* multilingual texts are objects by language (``{"fra": ...}``, ``{"mul": [...]}``); dates
  carry an offset that is not always right (« 2026-11-30+02:00 »): a French deadline is read
  as Paris time. Links may hold ``&amp;``.
"""

import html
import logging
import re
import time
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.domain.places import department_of
from app.schemas.tenders import LotIn, NoticeType, TenderIn

logger = logging.getLogger("pilao.ted")
PARIS = ZoneInfo("Europe/Paris")
PAGE_SIZE = 250  # the API maximum
MAX_ATTEMPTS = 4

FIELDS = [
    "publication-number",
    "notice-type",
    "notice-identifier",
    "procedure-identifier",
    "change-notice-version-identifier",
    "change-description",
    "publication-date",
    "notice-title",
    "title-proc",
    "description-proc",
    "identifier-lot",
    "title-lot",
    "buyer-name",
    "buyer-identifier",
    "buyer-post-code",
    "buyer-city",
    "place-of-performance",
    "place-of-performance-post-code-lot",
    "place-of-performance-post-code-proc",
    "classification-cpv",
    "contract-nature-main-proc",
    "procedure-type",
    "estimated-value-proc",
    "estimated-value-cur-proc",
    "estimated-value-lot",
    "deadline-receipt-tender-date-lot",
    "deadline-receipt-tender-time-lot",
    "document-url-lot",
]
PROCEDURES = {
    "open": "Procédure ouverte",
    "restricted": "Procédure restreinte",
    "neg-w-call": "Procédure avec négociation",
    "neg-wo-call": "Procédure négociée sans publication préalable",
    "comp-dial": "Dialogue compétitif",
    "innovation": "Partenariat d'innovation",
    "oth-single": "Autre procédure",
    "oth-mult": "Autre procédure",
}
NATURES: dict[str, Literal["services", "works", "supplies"]] = {
    "services": "services",
    "works": "works",
    "supplies": "supplies",
}


class TedUnavailable(Exception):
    """TED did not answer usably (network, 5xx, quota, unexpected reply)."""


def build_query(cpv_codes: list[str], since: date) -> str:
    """French notices published since ``since`` for these CPV codes (and their children)."""
    codes = sorted({c[:8] for c in cpv_codes if re.fullmatch(r"\d{8}", c[:8])})
    if not codes:
        raise ValueError("no CPV code to search")
    return (
        f"place-of-performance IN (FRA) AND classification-cpv IN ({' '.join(codes)}) "
        f"AND publication-date >= {since:%Y%m%d}"
    )


class TedClient:
    def __init__(
        self,
        base_url: str | None = None,
        http: httpx.Client | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self._base = (base_url or get_settings().ted_api_url).rstrip("/")
        self._http = http or httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))
        self._sleep = sleep

    def search(self, query: str, limit: int | None = None) -> Iterator[dict[str, Any]]:
        """Every notice matching ``query``, page after page (``limit``: stop after that many)."""
        token: str | None = None
        seen = 0
        while True:
            body: dict[str, Any] = {
                "query": query,
                "fields": FIELDS,
                "limit": PAGE_SIZE if limit is None else min(PAGE_SIZE, limit),
                "paginationMode": "ITERATION",
            }
            if token:
                body["iterationNextToken"] = token
            page = self._post(body)
            notices = page.get("notices")
            if not isinstance(notices, list):
                raise TedUnavailable("reply without notices")
            for notice in notices:
                if isinstance(notice, dict):
                    yield notice
                    seen += 1
                    if limit is not None and seen >= limit:
                        return
            token = page.get("iterationNextToken")
            if not notices or not token:
                return

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                res = self._http.post(f"{self._base}/v3/notices/search", json=body)
                if res.status_code == 429 or res.status_code >= 500:
                    last = TedUnavailable(f"HTTP {res.status_code}")
                    logger.warning("TED %s, attempt %d", res.status_code, attempt + 1)
                    if attempt < MAX_ATTEMPTS - 1:
                        self._sleep(min(2**attempt * 2, 30))
                    continue
                if res.status_code >= 400:  # a refused query does not get better by retrying
                    raise TedUnavailable(f"HTTP {res.status_code}: {res.text[:300]}")
                data = res.json()
                if not isinstance(data, dict):
                    raise TedUnavailable("reply is not an object")
                return data
            except (httpx.HTTPError, ValueError) as exc:  # transport, timeout, bad JSON
                last = exc
                logger.warning("TED error: %s", exc)
                if attempt < MAX_ATTEMPTS - 1:
                    self._sleep(min(2**attempt * 2, 30))
        raise TedUnavailable(str(last)) from last


# ---------- conversion ------------------------------------------------------------------


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _texts(value: Any) -> list[str]:
    """French text first, else the multilingual one, else English, else any language."""
    if isinstance(value, dict):
        for lang in ("fra", "mul", "eng", *value.keys()):
            if lang in value:
                return [str(v).strip() for v in _list(value[lang]) if str(v).strip()]
        return []
    return [str(v).strip() for v in _list(value) if str(v).strip()]


def _text(value: Any) -> str | None:
    texts = _texts(value)
    return texts[0] if texts else None


def department(postal_code: str) -> str | None:
    return department_of(postal_code)


def _deadline(dates: Any, times: Any) -> datetime | None:
    """The earliest lot deadline, read as Paris time (the stated offsets are unreliable)."""
    found: list[datetime] = []
    times_list = _list(times)
    for i, raw in enumerate(_list(dates)):
        day = re.match(r"(\d{4}-\d{2}-\d{2})", str(raw))
        if not day:
            continue
        clock = re.match(r"(\d{2}):(\d{2})", str(times_list[i])) if i < len(times_list) else None
        hour, minute = (int(clock[1]), int(clock[2])) if clock else (23, 59)
        d = date.fromisoformat(day[1])
        found.append(datetime(d.year, d.month, d.day, hour, minute, tzinfo=PARIS))
    return min(found) if found else None


def _published(raw: Any) -> datetime | None:
    day = re.match(r"(\d{4}-\d{2}-\d{2})", str(_list(raw)[0])) if _list(raw) else None
    if not day:
        return None
    d = date.fromisoformat(day[1])
    return datetime(d.year, d.month, d.day, tzinfo=PARIS)


def _amount(value: Any) -> float | None:
    for raw in _list(value):
        try:
            amount = float(str(raw).replace(",", "."))
        except ValueError:
            continue
        if amount >= 0:
            return amount
    return None


def _link(value: Any) -> str | None:
    for raw in _list(value):
        url = html.unescape(str(raw)).strip()
        if re.match(r"^https?://\S+$", url, re.IGNORECASE):
            return url
    return None


def _notice_type(kind: str) -> NoticeType:
    if kind.startswith("cn-"):
        return "contract_notice"
    if kind.startswith("can-"):
        return "award"
    return "other"


def _title(n: dict[str, Any]) -> str | None:
    title = _text(n.get("title-proc"))
    if title:
        return title
    # « France – Services de nettoyage de bâtiments – OBJET » : keep the object only
    full = _text(n.get("notice-title"))
    return full.split(" – ", 2)[-1] if full else _text(n.get("description-proc"))


def to_tender(n: dict[str, Any]) -> TenderIn | None:
    """One TED notice in Pilao's common format; None when it cannot be used (no title, id)."""
    procedure_id = str(n.get("procedure-identifier") or "").strip()
    publication = str(n.get("publication-number") or "").strip()
    title = _title(n)
    if not (procedure_id or publication) or not title:
        return None
    kind = _notice_type(str(n.get("notice-type") or ""))
    is_change = bool(n.get("change-notice-version-identifier"))
    postal = [
        *_list(n.get("place-of-performance-post-code-lot")),
        *_list(n.get("place-of-performance-post-code-proc")),
    ] or _list(n.get("buyer-post-code"))
    departments = list(dict.fromkeys(d for p in postal if (d := department(str(p)))))
    ids, lot_titles = _list(n.get("identifier-lot")), _texts(n.get("title-lot"))
    lot_values = _list(n.get("estimated-value-lot"))
    lots = (
        [
            LotIn(
                number=str(ids[i]) if i < len(ids) else None,
                title=t[:1000],
                estimated_amount_eur=(
                    _amount(lot_values[i]) if len(lot_values) == len(lot_titles) else None
                ),
            )
            for i, t in enumerate(lot_titles)
        ]
        if len(lot_titles) > 1
        else []
    )
    amount = _amount(n.get("estimated-value-proc"))
    currency = str(n.get("estimated-value-cur-proc") or "EUR")
    if amount is None and lots and all(lot.estimated_amount_eur is not None for lot in lots):
        amount = sum(lot.estimated_amount_eur or 0 for lot in lots)
    siret = next(
        (str(b) for b in _list(n.get("buyer-identifier")) if re.fullmatch(r"\d{14}", str(b))), None
    )
    nature = str(n.get("contract-nature-main-proc") or "")
    links = n.get("links")
    html_links = links.get("html") if isinstance(links, dict) else None
    html_links = html_links if isinstance(html_links, dict) else {}
    # One Pilao notice per procedure. A change notice keeps its own number (each one is
    # announced to the followers) and points at the procedure. Awards are not procedures to
    # answer: kept under their own number (V2, never watched).
    change = is_change and kind == "contract_notice" and bool(procedure_id)
    if change or kind == "award" or not procedure_id:
        source_id = publication or procedure_id
    else:
        source_id = procedure_id
    return TenderIn(
        source="ted",
        source_id=source_id,
        notice_type="correction" if change else kind,
        corrects=procedure_id if change else None,
        complete=True,  # a TED change notice repeats the whole notice
        title=title[:2000],
        description=(_text(n.get("description-proc")) or None),
        buyer_name=_text(n.get("buyer-name")),
        buyer_siret=siret,
        procedure=PROCEDURES.get(str(n.get("procedure-type") or "")),
        contract_nature=NATURES.get(nature),
        cpv_codes=[str(c) for c in _list(n.get("classification-cpv"))],
        departments=departments,
        nuts_codes=list(
            dict.fromkeys(
                str(c)
                for c in _list(n.get("place-of-performance"))
                if re.fullmatch(r"FR\w{3}", str(c))
            )
        ),
        estimated_amount_eur=amount if currency == "EUR" else None,
        published_at=_published(n.get("publication-date")),
        deadline_at=_deadline(
            n.get("deadline-receipt-tender-date-lot"), n.get("deadline-receipt-tender-time-lot")
        ),
        notice_url=_link(html_links.get("FRA"))
        or (f"https://ted.europa.eu/fr/notice/-/detail/{publication}" if publication else None),
        documents_url=_link(n.get("document-url-lot")),
        lots=lots,
        raw={
            "publication_number": publication,
            "notice_type": n.get("notice-type"),
            "notice_identifier": n.get("notice-identifier"),
            "change": _texts(n.get("change-description")),
        },
    )


class TedReader:
    """The TED source for ``services/tender_import.py``."""

    def __init__(self, client: TedClient | None = None) -> None:
        self._client = client or TedClient()

    def fetch(
        self, cpv_codes: list[str], since: date, limit: int | None = None
    ) -> Iterator[TenderIn | None]:
        for notice in self._client.search(build_query(cpv_codes, since), limit):
            try:
                yield to_tender(notice)
            except ValidationError as exc:  # one odd notice never stops the pass
                logger.warning(
                    "TED notice %s not converted: %s", notice.get("publication-number"), exc
                )
                yield None
