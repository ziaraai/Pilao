"""Consultations (ADR-052): a general contractor asks for a quote on part of a lot."""

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.api.helpers import signed_in_client
from tests.conftest import Outbox

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
