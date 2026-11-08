"""TED reader (P3-02): real notices fetched on 2026-11-08, converted to the common format."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.integrations.ted import TedClient, TedUnavailable, build_query, department, to_tender

PARIS = ZoneInfo("Europe/Paris")
PAGE: dict[str, Any] = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "ted_notices.json").read_text("utf-8")
)
BY_NUMBER = {n["publication-number"]: n for n in PAGE["notices"]}


def test_a_cleaning_notice_in_saint_etienne() -> None:
    t = to_tender(BY_NUMBER["738785-2026"])
    assert t is not None
    # a change notice of its procedure: it points at the procedure, under its own number
    assert (t.notice_type, t.source_id, t.corrects, t.complete) == (
        "correction",
        "738785-2026",
        "b67bfaba-c5de-4e8d-b05f-5560e23cf7cf",
        True,
    )
    assert t.title == "NETTOYAGE DES LOCAUX ADMINISTRATIFS D'HABITAT ET MÉTROPOLE"
    assert t.buyer_name == "HABITAT ET METROPOLE SAINT-ETIENNE"
    assert t.departments == ["42"] and t.nuts_codes == ["FRK25"]
    assert t.cpv_codes == ["90911000", "90910000", "90911300"]
    assert t.contract_nature == "services" and t.procedure == "Procédure ouverte"
    assert t.estimated_amount_eur == 1_200_000
    assert t.deadline_at == datetime(2026, 11, 6, 12, 0, tzinfo=PARIS)  # « 12h00 », Paris
    assert t.published_at == datetime(2026, 10, 26, tzinfo=PARIS)
    assert [lot.number for lot in t.lots] == ["LOT-0001", "LOT-0002", "LOT-0003"]
    assert t.lots[0].title == "NETTOYAGE DU SIEGE SOCIAL NEOZ (HORS VITRERIE)"
    assert t.documents_url and "&amp;" not in t.documents_url  # HTML entities decoded
    assert t.notice_url == "https://ted.europa.eu/fr/notice/-/detail/738785-2026"
    assert t.raw["change"][0].startswith("Remise des offres: Au lieu du 30/10/2026")


def test_a_procedure_and_its_changes_share_one_notice() -> None:
    original = to_tender(BY_NUMBER["447747-2026"])
    first, second = to_tender(BY_NUMBER["497104-2026"]), to_tender(BY_NUMBER["534002-2026"])
    assert original and first and second
    procedure = "32bb2a4a-93d4-4ea5-ac34-bac809905d6c"
    assert (original.notice_type, original.source_id) == ("contract_notice", procedure)
    assert {first.corrects, second.corrects} == {procedure}
    assert first.source_id != second.source_id  # each change is announced once
    # « Au lieu du 31/07/2026 à 11h00 … Lire 17/08/2026 à 17h00 »
    assert original.deadline_at == datetime(2026, 7, 31, 11, 0, tzinfo=PARIS)
    assert first.deadline_at == datetime(2026, 8, 17, 17, 0, tzinfo=PARIS)
    assert second.deadline_at == datetime(2026, 8, 26, 11, 0, tzinfo=PARIS)
    assert original.departments == ["30"] and original.contract_nature == "works"
    assert len(original.lots) > 10 and original.buyer_siret is None  # « 63373 » is no SIRET


def test_an_award_is_kept_apart() -> None:
    t = to_tender(BY_NUMBER["756561-2026"])
    assert t is not None
    assert (t.notice_type, t.source_id) == ("award", "756561-2026")
    assert t.buyer_siret == "13001550600012" and t.departments == ["54"]


def test_departments_from_postal_codes() -> None:
    cases = {
        "42000": "42",
        "75013": "75",
        "20090": "2A",
        "20200": "2B",
        "97400": "974",
        "97150": "971",
        "97500": None,  # Saint-Pierre-et-Miquelon: not a department
        "98000": None,  # Monaco
        "4200": None,
        "ABCDE": None,
    }
    assert {code: department(code) for code in cases} == cases


def test_unusable_notices_are_skipped() -> None:
    assert to_tender({"publication-number": "1-2026"}) is None  # no title
    assert to_tender({"title-proc": {"fra": "Nettoyage"}}) is None  # no identifier


def test_the_query_covers_the_cpv_families_since_a_date() -> None:
    q = build_query(["90911200", "90910000", "90910000", "bad", "45453000-7"], date(2026, 11, 1))
    assert q == (
        "place-of-performance IN (FRA) AND classification-cpv IN (45453000 90910000 90911200) "
        "AND publication-date >= 20261101"
    )
    with pytest.raises(ValueError):
        build_query([], date(2026, 11, 1))


def client(handler: Any, sleeps: list[float] | None = None) -> TedClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return TedClient("https://ted.test", http, sleep=(sleeps if sleeps is not None else []).append)


def test_the_client_follows_the_pages_and_retries() -> None:
    calls: list[dict[str, Any]] = []
    notices = PAGE["notices"]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        assert request.url.path == "/v3/notices/search"
        if len(calls) == 1:
            return httpx.Response(503)  # retried
        if "iterationNextToken" not in body:
            return httpx.Response(200, json={"notices": notices[:3], "iterationNextToken": "next"})
        return httpx.Response(200, json={"notices": notices[3:], "iterationNextToken": None})

    sleeps: list[float] = []
    got = list(client(handler, sleeps).search("q"))
    assert [n["publication-number"] for n in got] == [n["publication-number"] for n in notices]
    assert calls[1]["paginationMode"] == "ITERATION" and calls[2]["iterationNextToken"] == "next"
    assert sleeps == [2]  # one wait, after the 503
    assert len(list(client(lambda r: httpx.Response(200, json=PAGE)).search("q", 2))) == 2


def test_the_client_gives_up_cleanly() -> None:
    with pytest.raises(TedUnavailable, match="HTTP 400"):  # a refused query: no retry
        list(client(lambda r: httpx.Response(400, text="bad query")).search("q"))
    sleeps: list[float] = []
    with pytest.raises(TedUnavailable):
        list(client(lambda r: httpx.Response(500), sleeps).search("q"))
    assert len(sleeps) == 3  # 4 attempts
    with pytest.raises(TedUnavailable):
        list(client(lambda r: httpx.Response(200, json={"oops": 1})).search("q"))
