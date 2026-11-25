"""A price file that is a document (25/11): a contractor's « fiche d'intervention » in PDF is
read from its pages, priced like any file, and gives a DPGF in Excel."""

import io
import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.ai import llm
from app.core.config import get_settings
from tests.api.helpers import signed_in_client
from tests.api.test_analysis import RC, zipped
from tests.api.test_bids import deposit, new_bid
from tests.api.test_pricing import credits_left, prices
from tests.conftest import FakeQueue, MemoryStorage, Outbox
from tests.documents_helpers import make_pdf

Factory = Callable[[], TestClient]
FICHE = make_pdf(
    [
        ["Fiche d'intervention etablie depuis le devis n DE36532",
         "Numero Description Qte Unite",
         "1 CUISINE 1,00",
         "1.1 Degraissage du sol et application d'un impermeabilisant 16,56 M2",
         "2 WC 1,00",
         "2.1 Degraissage du sol et application d'un impermeabilisant 1,65 M2",
         "3 Traitement et valorisation des dechets 1,00 U"],
    ]
)  # fmt: skip
LABEL = "Degraissage du sol et application d'un impermeabilisant"


class DocumentModel:
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.lines: list[dict[str, Any]] = [
            {"section": "CUISINE", "label": LABEL, "unit": "M2", "quantity": "16,56", "page": 1},
            {"section": "WC", "label": LABEL, "unit": "M2", "quantity": "1,65", "page": 1},
            {"label": "Traitement et valorisation des dechets", "unit": "U", "quantity": "1,00",
             "page": 1},
            {"section": "SALON", "label": "Cristallisation du marbre", "unit": "m²", "page": 1},
        ]  # fmt: skip

    def __call__(
        self, model: str, messages: list[dict[str, Any]], max_tokens: int | None = None
    ) -> tuple[str, int, int, float]:
        self.prompts.append(messages[-1]["content"])
        return json.dumps({"lines": self.lines, "notes": ["Prix HT"]}), 900, 200, 0.001


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> DocumentModel:
    fake = DocumentModel()
    monkeypatch.setattr(get_settings(), "llm_model_extraction", "test/extraction")
    monkeypatch.setattr(llm, "_call_provider", fake)
    return fake


def test_a_pdf_price_file_is_read_from_its_pages_and_gives_a_dpgf(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    storage: MemoryStorage,
    model: DocumentModel,
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c, kind="consultation", title="Traitement de sol", buyer_name="CCTB")
    deposit(c, bid, ("DCE.zip", zipped({"RC.pdf": RC, "DPGF.pdf": FICHE})))
    queue.drain_dce()
    listed = prices(c, bid)["files"]
    assert [(f["path"], f["fillable"], f["readable"]) for f in listed] == [
        ("DPGF.pdf", False, True)
    ]
    before = credits_left(c)
    res = c.post(f"/bids/{bid}/prices/{listed[0]['dce_file_id']}/read")
    assert res.status_code == 202, res.text
    queue.drain_price_reads()
    assert credits_left(c) == before - 1
    sent = model.prompts[-1]
    assert "<pages>" in sent and "[p.1]" in sent and "16,56" in sent
    sheet = prices(c, bid)["files"][0]["sheet"]
    assert sheet["status"] == "ready" and sheet["mode"] == "document"
    assert [(ln["section"], ln["quantity"]) for ln in sheet["lines"]] == [
        ("CUISINE", "16.56"),
        ("WC", "1.65"),
        ("", "1"),
    ]
    assert any("pas été retrouvée" in w for w in sheet["warnings"])  # the invented SALON
    entries = {ln["id"]: {"price_cents": 1250} for ln in sheet["lines"]}
    res = c.put(f"/price-sheets/{sheet['id']}", json={"entries": entries})
    assert res.status_code == 200, res.text
    assert res.json()["total_cents"] == 20700 + 2063 + 1250  # 20,625 € rounds up

    res = c.post(f"/price-sheets/{sheet['id']}/export")
    assert res.status_code == 200, res.text
    url = res.json()["url"]
    assert "DPGF" in url
    key = url.split("https://storage.test/")[1].split("?")[0]
    ws = load_workbook(io.BytesIO(storage.objects[key]))["DPGF"]
    labels = [ws.cell(r, 2).value for r in range(1, ws.max_row + 1)]
    assert LABEL in labels and "Traitement et valorisation des dechets" in labels
    texts = " ".join(str(v) for v in labels if v)
    assert "CCTB" in texts and "DPGF.pdf" in texts


def test_the_quote_of_a_pdf_consultation_bundles_the_dpgf(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    storage: MemoryStorage,
    model: DocumentModel,
) -> None:
    import zipfile

    from tests.api.test_exports import FakeConverter
    from tests.api.test_quotes import downloaded

    c = signed_in_client(make_client, outbox)
    bid = new_bid(c, kind="consultation", title="Traitement de sol", buyer_name="CCTB")
    deposit(c, bid, ("DCE.zip", zipped({"DPGF.pdf": FICHE})))
    queue.drain_dce()
    file_id = prices(c, bid)["files"][0]["dce_file_id"]
    c.post(f"/bids/{bid}/prices/{file_id}/read")
    queue.drain_price_reads()
    sheet = prices(c, bid)["files"][0]["sheet"]
    c.put(
        f"/price-sheets/{sheet['id']}",
        json={"entries": {ln["id"]: {"price_cents": 1000} for ln in sheet["lines"]}},
    )
    assert c.post(f"/bids/{bid}/quote", json={}).status_code == 202
    queue.drain_quotes(FakeConverter())
    names = zipfile.ZipFile(io.BytesIO(downloaded(c, storage, bid, "zip"))).namelist()
    assert "DPGF - DPGF.xlsx" in names  # the DPGF Pilao wrote, never « rempli »
