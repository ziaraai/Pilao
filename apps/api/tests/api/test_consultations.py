"""Consultations (ADR-052): a general contractor asks for a quote on part of a lot."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai import llm
from app.core.config import get_settings
from tests.api.helpers import signed_in_client
from tests.api.test_pricing import LINES, bid_with_prices, read
from tests.conftest import FakeQueue, Outbox

Factory = Callable[[], TestClient]


def test_a_consultation_is_a_dossier_with_its_client_and_contact(
    make_client: Factory, outbox: Outbox
) -> None:
    c = signed_in_client(make_client, outbox)
    res = c.post(
        "/bids",
        json={
            "kind": "consultation",
            "title": "Annexe du lycée Récamier — nettoyage",
            "buyer_name": "Entreprise générale Exemple",
            "contact_name": "Mme Exemple",
            "contact_email": "contact@eg-exemple.fr",
            "lot_label": "Lot 16 — Plâtrerie, peinture, plafonds",
        },
    )
    assert res.status_code == 201, res.text
    bid = res.json()
    assert bid["kind"] == "consultation"
    assert (bid["contact_name"], bid["contact_email"]) == ("Mme Exemple", "contact@eg-exemple.fr")
    listed = c.get("/bids").json()
    assert [b["kind"] for b in listed] == ["consultation"]


def test_a_dossier_is_a_tender_unless_said_otherwise(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    bid = c.post("/bids", json={"title": "Nettoyage des écoles"}).json()
    assert bid["kind"] == "tender" and bid["contact_email"] is None


def test_a_bad_contact_email_is_refused(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    res = c.post(
        "/bids", json={"kind": "consultation", "title": "X", "contact_email": "pas-un-mail"}
    )
    assert res.status_code == 422
    assert c.post("/bids", json={"kind": "autre", "title": "X"}).status_code == 422


# ---- « Ma liste de prix » and the reading of a consultation's price file -------------------




SERVICES = [
    {"name": "Nettoyage quotidien de locaux", "unit": "jour", "price_cents": 9000,
     "description": "Entretien courant des locaux"},
    {"name": "Vitrerie", "unit": "m²", "price_cents": 150, "description": None},
]  # fmt: skip


class ReadAndMatch:
    """The price-file reading, then the matching with the price list."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(
        self, model: str, messages: list[dict[str, Any]], max_tokens: int | None = None
    ) -> tuple[str, int, int, float]:
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        if "<services>" in prompt:
            first = next(line for line in prompt.splitlines() if "Nettoyage quotidien" in line)
            sid = first.split(" · ")[0].strip()
            reply: dict[str, Any] = {"matches": [
                {"line": "DQE!B5", "service": sid},
                {"line": "DQE!B6", "service": sid},
                {"line": "DQE!B42", "service": sid},  # hourly line, unit « heure »: refused
            ]}  # fmt: skip
        else:
            reply = {"lines": LINES, "notes": []}
        return json.dumps(reply), 800, 200, 0.001


@pytest.fixture
def reader(monkeypatch: pytest.MonkeyPatch) -> ReadAndMatch:
    fake = ReadAndMatch()
    monkeypatch.setattr(get_settings(), "llm_model_extraction", "test/extraction")
    monkeypatch.setattr(llm, "_call_provider", fake)
    return fake


def test_the_price_list_is_saved_whole_and_checked(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    assert c.get("/profile/services").json() == []
    res = c.put("/profile/services", json={"services": SERVICES})
    assert res.status_code == 200, res.text
    saved = res.json()
    assert [(s["name"], s["unit"], s["price_cents"]) for s in saved] == [
        ("Nettoyage quotidien de locaux", "jour", 9000),
        ("Vitrerie", "m²", 150),
    ]
    assert c.get("/profile/services").json() == saved
    bad = {"services": [{"name": "X", "unit": "litre", "price_cents": 1}]}
    assert c.put("/profile/services", json=bad).status_code == 422
    neg = {"services": [{"name": "X", "unit": "m²", "price_cents": -1}]}
    assert c.put("/profile/services", json=neg).status_code == 422
    assert c.put("/profile/services", json={"services": []}).json() == []


def test_a_consultation_reads_prefills_and_sets_other_rubriques_aside(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: ReadAndMatch
) -> None:
    c = signed_in_client(make_client, outbox)
    c.put("/profile/services", json={"services": SERVICES})
    bid = bid_with_prices(c, queue, kind="consultation")
    sheet = read(c, queue, bid)
    assert any("<services>" in p for p in reader.prompts)
    by_id = {ln["id"]: ln for ln in sheet["lines"]}
    assert by_id["DQE!B5"]["price_cents"] == 9000 and by_id["DQE!B5"]["source"] == "price"
    assert by_id["DQE!B5"]["service_name"] == "Nettoyage quotidien de locaux"
    assert by_id["DQE!B42"]["service_name"] is None  # an hourly line: never a « jour » price
    assert sheet["excluded_sections"] == ["prestation annuelle", "interventions"]
    assert by_id["DQE!B32"]["excluded"] and by_id["DQE!B42"]["excluded"]
    assert sheet["total_cents"] == 9000 * 208 + 9000 * 188
    assert sheet["missing_count"] == 0

    # the company takes the yearly rubrique back, then sets « interventions » aside again
    res = c.put(f"/price-sheets/{sheet['id']}", json={"excluded_sections": ["interventions"]})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["excluded_sections"] == ["interventions"]
    assert out["missing_count"] == 1  # the yearly line is to price now
    bad = c.put(f"/price-sheets/{sheet['id']}", json={"excluded_sections": ["pas une rubrique"]})
    assert bad.status_code == 422


def test_a_tender_gets_the_prices_but_sets_nothing_aside(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: ReadAndMatch
) -> None:
    c = signed_in_client(make_client, outbox)
    c.put("/profile/services", json={"services": SERVICES})
    sheet = read(c, queue, bid_with_prices(c, queue))
    assert sheet["excluded_sections"] == []
    assert {ln["id"]: ln for ln in sheet["lines"]}["DQE!B6"]["price_cents"] == 9000


def test_without_a_price_list_there_is_no_matching_call(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: ReadAndMatch
) -> None:
    c = signed_in_client(make_client, outbox)
    sheet = read(c, queue, bid_with_prices(c, queue, kind="consultation"))
    assert not any("<services>" in p for p in reader.prompts)
    assert sheet["excluded_sections"] == [] and sheet["missing_count"] == 4  # no rate: all 4
