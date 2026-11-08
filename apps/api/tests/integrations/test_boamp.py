"""BOAMP reader (P3-01). The records below are WRITTEN BY HAND from the dataset's
documentation: the real format is still to be checked from the server
(``import-tenders --source boamp --essai``). These tests only pin the tolerant behaviour:
a missing or odd field never breaks the import."""

import json
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


def test_the_reader_pages_by_publication_date() -> None:
    asked: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        asked.append(params)
        offset = int(params["offset"])
        page = [RECORD] * (100 if offset == 0 else 30)
        return httpx.Response(200, json={"total_count": 130, "results": page})

    client = BoampClient("https://boamp.test", httpx.Client(transport=httpx.MockTransport(handler)))
    got = list(BoampReader(client).fetch([], date(2026, 11, 7)))
    assert len(got) == 130 and [a["offset"] for a in asked] == ["0", "100"]
    assert asked[0]["where"] == "dateparution >= date'2026-11-07'"
    with pytest.raises(BoampUnavailable):
        sleeps: list[float] = []
        down = BoampClient(
            "https://boamp.test",
            httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))),
            sleep=sleeps.append,
        )
        list(BoampReader(down).fetch([], date(2026, 11, 7)))
