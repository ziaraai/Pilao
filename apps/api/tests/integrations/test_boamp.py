"""BOAMP reader (P3-01). The records below are WRITTEN BY HAND from the dataset's
documentation: the real format is still to be checked from the server
(``import-tenders --source boamp --essai``). These tests only pin the tolerant behaviour:
a missing or odd field never breaks the import."""

import json
import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.integrations.boamp import BoampClient, BoampReader, BoampUnavailable, to_tender

PARIS = ZoneInfo("Europe/Paris")
RECORD: dict[str, Any] = {
    "idweb": "26-123456",
    "objet": "Nettoyage des locaux de la mairie",
    "nomacheteur": "Commune de Villars",
    "dateparution": "2026-11-05",
    "datelimitereponse": "2026-12-01T12:00:00+01:00",
    "code_departement": ["42"],
    "type_marche": ["SERVICES"],
    "nature": "APPEL_OFFRE",
    "procedure_libelle": "Procédure adaptée",
    "url_avis": "https://www.boamp.fr/pages/avis/?q=idweb:26-123456",
    "donnees": json.dumps(
        {
            "FNSimple": {
                "initial": {
                    "description": {"CPV": {"objetPrincipal": {"classPrincipale": "90911200"}}}
                }
            }
        }
    ),
}


def test_a_call_for_tenders() -> None:
    t = to_tender(RECORD)
    assert t is not None
    assert (t.source, t.source_id, t.notice_type) == ("boamp", "26-123456", "contract_notice")
    assert t.departments == ["42"] and t.cpv_codes == ["90911200"]
    assert t.contract_nature == "services" and t.buyer_name == "Commune de Villars"
    assert t.deadline_at == datetime(2026, 12, 1, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))


def test_corrections_awards_and_odd_records() -> None:
    fix = to_tender(
        {**RECORD, "idweb": "26-130000", "nature": "RECTIFICATIF", "annonce_lie": "26-123456"}
    )
    assert fix is not None and (fix.notice_type, fix.corrects) == ("correction", "26-123456")
    # a correction that does not say what it corrects stays a notice of its own
    alone = to_tender({**RECORD, "nature": "RECTIFICATIF"})
    assert alone is not None and alone.notice_type == "contract_notice"
    award = to_tender({**RECORD, "nature": "ATTRIBUTION"})
    assert award is not None and award.notice_type == "award"
    odd = to_tender(
        {"idweb": "26-1", "objet": "Objet", "datelimitereponse": "pas une date", "donnees": None}
    )
    assert odd is not None and odd.deadline_at is None and odd.cpv_codes == []
    day_only = to_tender({**RECORD, "datelimitereponse": "2026-12-01"})
    assert day_only is not None and day_only.deadline_at == datetime(
        2026, 12, 1, 23, 59, tzinfo=PARIS
    )
    assert to_tender({"objet": "sans numéro"}) is None and to_tender({"idweb": "x"}) is None


def test_records_are_read_day_by_day_and_page_by_page() -> None:
    asked: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        asked.append(params)
        day, offset = params["where"][-11:-1], int(params["offset"])
        size = {"2026-11-06": 130, "2026-11-07": 0, "2026-11-08": 5}[day]
        page = [RECORD] * max(0, min(100, size - offset))
        return httpx.Response(200, json={"total_count": size, "results": page})

    client = BoampClient("https://boamp.test", httpx.Client(transport=httpx.MockTransport(handler)))
    got = list(client.records(date(2026, 11, 6), until=date(2026, 11, 8)))
    assert len(got) == 135
    assert [(a["where"], a["offset"]) for a in asked] == [
        ("dateparution = date'2026-11-06'", "0"),
        ("dateparution = date'2026-11-06'", "100"),
        ("dateparution = date'2026-11-07'", "0"),
        ("dateparution = date'2026-11-08'", "0"),
    ]
    assert len(list(client.records(date(2026, 11, 6), 3, until=date(2026, 11, 8)))) == 3


def test_the_reader_fetches_only_new_open_notices_in_full() -> None:
    """A light list of each day, then the whole notice only when it is worth it."""
    listing = [
        {
            "idweb": "26-1",
            "datelimitereponse": "2026-12-01T11:00:00+00:00",
            "nature": "APPEL_OFFRE",
        },
        {
            "idweb": "26-2",
            "datelimitereponse": "2026-11-01T11:00:00+00:00",
            "nature": "APPEL_OFFRE",
        },
        {"idweb": "26-3", "datelimitereponse": None, "nature": "ATTRIBUTION"},
        {"idweb": "26-4", "datelimitereponse": None, "nature": "RECTIFICATIF"},
        {
            "idweb": "26-5",
            "datelimitereponse": "2026-12-05T11:00:00+00:00",
            "nature": "APPEL_OFFRE",
        },
    ]
    full: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("select"):  # the light list of the day
            assert params["select"] == "idweb,datelimitereponse,nature,nature_libelle"
            rows = listing if params["where"] == "dateparution = date'2026-11-08'" else []
            return httpx.Response(200, json={"results": rows})
        ids = re.findall(r'idweb = "([^"]+)"', params["where"])
        full.extend(ids)
        return httpx.Response(200, json={"results": [{**RECORD, "idweb": i} for i in ids]})

    client = BoampClient("https://boamp.test", httpx.Client(transport=httpx.MockTransport(handler)))
    now = datetime(2026, 11, 8, 10, 0, tzinfo=PARIS)
    got = list(
        BoampReader(client).fetch([], date(2026, 11, 7), known=lambda ids: {"26-5"}, now=now)
    )
    # closed (26-2), award (26-3) and already stored (26-5): never read in full
    assert full == ["26-1", "26-4"] and [t.source_id for t in got if t] == ["26-1", "26-4"]


def test_a_failing_boamp_is_reported() -> None:
    sleeps: list[float] = []
    down = BoampClient(
        "https://boamp.test",
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))),
        sleep=sleeps.append,
    )
    with pytest.raises(BoampUnavailable):
        list(BoampReader(down).fetch([], date(2026, 11, 7)))
    assert len(sleeps) == 3


def test_the_place_of_work_comes_first() -> None:
    t = to_tender({**RECORD, "code_departement": ["33"], "code_departement_prestation": ["2B"]})
    assert t is not None and t.departments == ["2B"]
    buyer_only = to_tender({**RECORD, "code_departement_prestation": None})
    assert buyer_only is not None and buyer_only.departments == ["42"]
    # seen on the server: BOAMP writes Corsica « 20A » / « 20B » (SYVADEC, 26-103246)
    corsica = to_tender({**RECORD, "code_departement": ["20B", "20A"]})
    assert corsica is not None and corsica.departments == ["2B", "2A"]
    assert to_tender({**RECORD, "code_departement": ["1", "971", "XX"]}).departments == [  # type: ignore[union-attr]
        "01",
        "971",
    ]


def test_deadlines_are_kept_as_the_instant_boamp_gives() -> None:
    """Seen on the server: « 2026-11-30T11:00:00+00:00 » is the « 12:00:00+01:00 » of the
    notice itself (donnees): noon in Paris."""
    t = to_tender({**RECORD, "datelimitereponse": "2026-11-30T11:00:00+00:00"})
    assert t is not None and t.deadline_at is not None
    assert t.deadline_at.astimezone(PARIS) == datetime(2026, 11, 30, 12, 0, tzinfo=PARIS)
