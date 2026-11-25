"""A consultation read from its documents (25/11): the client's facts in the dossier, the
document of quantities found and read, one credit for the whole."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.config import get_settings
from app.db.models import DceFile
from tests.api.helpers import signed_in_client
from tests.api.test_analysis import zipped
from tests.api.test_pricing import credits_left, prices
from tests.conftest import FakeQueue, Outbox
from tests.documents_helpers import make_pdf

Factory = Callable[[], TestClient]
FICHE = make_pdf(
    [
        ["CCTB - Rue de l'orphelinat - 42100 SAINT ETIENNE - Tel : 04 77 25 05 44",
         "Fiche d'intervention etablie depuis le devis n : DE36594",
         "Adresse du chantier : Monsieur DELBARRE Jean",
         "Adresse de facturation : 7 rue du General Leclerc 42100 Saint Etienne",
         "1 PIECE PRINCIPALE ET MEZZANINE 1,00",
         "1.1 Nettoyage et cristallisation du sol 89,83 M2",
         "3 Traitement et valorisation des dechets 1,00 U"],
    ]
)  # fmt: skip
PLAN = make_pdf([["Plan du rez-de-chaussee, echelle 1/100"]])


class Model:
    """Reads the consultation, then the price document."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.fail = False
        self.price_files = [{"file": "FICHE.pdf", "reason": "postes avec quantités"}]

    def __call__(
        self, model: str, messages: list[dict[str, Any]], max_tokens: int | None = None
    ) -> tuple[str, int, int, float]:
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        if self.fail:
            raise llm.LlmProviderError("down")
        if "<files>" in prompt:
            src = {"file": "FICHE.pdf", "page": 1}
            reply: dict[str, Any] = {
                "facts": {
                    "title": {"value": "Nettoyage et cristallisation du sol", **src},
                    "client_name": {"value": "CCTB", **src},
                    "client_address": {"value": "Rue de l'orphelinat, 42100 Saint Etienne", **src},
                    "site_address": {
                        "value": "Monsieur DELBARRE Jean, 7 rue du General Leclerc 42100 Saint Etienne",
                        **src,
                    },
                    "contact_phone": {"value": "04 77 25 05 44", **src},
                    "reference": {"value": "DE36594", **src},
                    "contact_email": {"value": "inconnu@cctb.fr", **src},  # not written: dropped
                },
                "price_files": self.price_files,
            }
        else:
            reply = {
                "lines": [
                    {"section": "PIECE PRINCIPALE ET MEZZANINE",
                     "label": "Nettoyage et cristallisation du sol", "unit": "M2",
                     "quantity": "89,83", "page": 1},
                    {"label": "Traitement et valorisation des dechets", "unit": "U",
                     "quantity": "1,00", "page": 1},
                ],
                "notes": [],
            }  # fmt: skip
        return json.dumps(reply), 900, 200, 0.001


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> Model:
    fake = Model()
    monkeypatch.setattr(get_settings(), "llm_model_extraction", "test/extraction")
    monkeypatch.setattr(llm, "_call_provider", fake)
    return fake


def created(c: TestClient, queue: FakeQueue, files: dict[str, bytes], **kw: Any) -> str:
    """« Nouvelle consultation »: the documents first, read at once (analyse=true)."""
    res = c.post("/bids", json={"kind": "consultation", **kw})
    assert res.status_code == 201, res.text
    bid = str(res.json()["id"])
    res = c.post(
        f"/bids/{bid}/dce",
        params={"analyse": "true"},
        files=[("files", ("DCE.zip", zipped(files), "application/zip"))],
    )
    assert res.status_code == 202, res.text
    queue.drain_dce()
    queue.drain_consultation_reads()
    queue.drain_price_reads()
    return bid


def test_the_documents_fill_the_dossier_and_the_price_file_is_read(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    before = credits_left(c)
    res = c.post("/bids", json={"kind": "consultation"})
    assert res.json()["title"].startswith("Consultation du ")  # no title typed yet
    bid = created(c, queue, {"FICHE.pdf": FICHE, "PLAN.pdf": PLAN})
    assert credits_left(c) == before - 1  # the reading and its price file: one credit

    dossier = c.get(f"/bids/{bid}").json()
    assert dossier["title"] == "Nettoyage et cristallisation du sol"
    assert dossier["buyer_name"] == "CCTB" and dossier["reference"] == "DE36594"
    assert dossier["contact_phone"] == "04 77 25 05 44" and dossier["contact_email"] is None
    assert dossier["site_address"].startswith("Monsieur DELBARRE Jean")
    assert dossier["facts_sources"]["buyer_name"] == {"file": "FICHE.pdf", "page": 1}
    state = c.get(f"/bids/{bid}/consultation-read").json()
    assert state["status"] == "ready"
    assert "contact_email" not in state["found"] and "reference" in state["found"]
    assert [p["path"] for p in state["price_files"]] == ["FICHE.pdf"]

    # the fiche became the price file, read without a second credit
    kinds = {f.path: f.detected_kind for f in db.scalars(select(DceFile))}
    assert kinds["FICHE.pdf"] == "dpgf" and kinds["PLAN.pdf"] != "dpgf"
    sheet = prices(c, bid)["files"][0]["sheet"]
    assert sheet["status"] == "ready" and sheet["mode"] == "document"
    assert [ln["quantity"] for ln in sheet["lines"]] == ["89.83", "1"]


def test_what_the_user_typed_is_never_replaced(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = created(c, queue, {"FICHE.pdf": FICHE}, title="Mon intitulé", buyer_name="CCTB Loire")
    dossier = c.get(f"/bids/{bid}").json()
    assert (dossier["title"], dossier["buyer_name"]) == ("Mon intitulé", "CCTB Loire")
    assert "buyer_name" not in dossier["facts_sources"]
    # a fact read, then corrected by the user: its source goes, and a new reading keeps it
    res = c.patch(f"/bids/{bid}", json={"reference": "DE-36594-B"})
    assert res.json()["facts_sources"].get("reference") is None
    assert c.post(f"/bids/{bid}/consultation-read").status_code == 202
    queue.drain_consultation_reads()
    assert c.get(f"/bids/{bid}").json()["reference"] == "DE-36594-B"


def test_several_price_files_wait_for_the_choice_and_the_first_reading_is_included(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model
) -> None:
    c = signed_in_client(make_client, outbox)
    model.price_files = [
        {"file": "FICHE.pdf", "reason": "postes"},
        {"file": "METRE.pdf", "reason": "métré"},
    ]
    before = credits_left(c)
    bid = created(c, queue, {"FICHE.pdf": FICHE, "METRE.pdf": FICHE})
    listed = prices(c, bid)["files"]
    assert sorted(f["path"] for f in listed) == ["FICHE.pdf", "METRE.pdf"]
    assert all(f["sheet"] is None for f in listed)  # Pilao asks which one
    assert credits_left(c) == before - 1
    c.post(f"/bids/{bid}/prices/{listed[0]['dce_file_id']}/read")
    queue.drain_price_reads()
    assert credits_left(c) == before - 1  # the chosen one: included
    c.post(f"/bids/{bid}/prices/{listed[1]['dce_file_id']}/read")
    queue.drain_price_reads()
    assert credits_left(c) == before - 2  # another one: its own credit


def test_a_failed_reading_gives_the_credit_back(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model
) -> None:
    c = signed_in_client(make_client, outbox)
    model.fail = True
    before = credits_left(c)
    bid = created(c, queue, {"FICHE.pdf": FICHE})
    state = c.get(f"/bids/{bid}/consultation-read").json()
    assert state["status"] == "error" and state["error"]
    assert credits_left(c) == before


def test_only_a_consultation_is_read_and_only_by_its_company(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model
) -> None:
    c = signed_in_client(make_client, outbox)
    tender = c.post("/bids", json={"title": "Appel d'offres"}).json()["id"]
    assert c.post(f"/bids/{tender}/consultation-read").status_code == 422
    assert c.post("/bids", json={"kind": "tender"}).status_code == 422  # a tender needs a title
    bid = created(c, queue, {"FICHE.pdf": FICHE})
    other = signed_in_client(make_client, outbox, 2)
    assert other.get(f"/bids/{bid}/consultation-read").status_code == 404
    assert other.post(f"/bids/{bid}/consultation-read").status_code == 404


def test_without_credits_the_reading_waits_and_a_click_is_refused(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model, db: Session
) -> None:
    from tests.api.test_credits_actions import set_price

    c = signed_in_client(make_client, outbox)
    set_price(db, "price_read", 10**9)
    before = credits_left(c)
    bid = created(c, queue, {"FICHE.pdf": FICHE})
    state = c.get(f"/bids/{bid}/consultation-read").json()
    assert state["status"] == "waiting_credits" and "Crédits épuisés" in state["error"]
    assert credits_left(c) == before and model.prompts == []
    res = c.post(f"/bids/{bid}/consultation-read")
    assert res.status_code == 402 and res.json()["error"]["code"] == "credits_exhausted"


def test_a_dead_reading_is_closed_and_refunded(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model, db: Session
) -> None:
    from app.db.models import ConsultationRead
    from app.services.stale_works import sweep_stale_works

    c = signed_in_client(make_client, outbox)
    before = credits_left(c)
    bid = c.post("/bids", json={"kind": "consultation"}).json()["id"]
    c.post(
        f"/bids/{bid}/dce",
        params={"analyse": "true"},
        files=[("files", ("DCE.zip", zipped({"FICHE.pdf": FICHE}), "application/zip"))],
    )
    queue.drain_dce()  # the reading is queued, then the worker dies
    assert credits_left(c) == before - 1
    db.execute(update(ConsultationRead).values(updated_at=datetime(2026, 1, 1, tzinfo=UTC)))
    db.commit()
    assert sweep_stale_works(db, queue) == 1
    assert credits_left(c) == before
    state = c.get(f"/bids/{bid}/consultation-read").json()
    assert state["status"] == "error" and "interrompue" in state["error"]
    queue.drain_consultation_reads()  # the forgotten job: nothing read
    assert model.prompts == []
