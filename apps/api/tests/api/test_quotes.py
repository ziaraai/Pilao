"""The company's quote for a consultation (ADR-052): numbered, sourced, paid once, refunded."""

import io
import json
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.config import get_settings
from tests.api.helpers import signed_in_client
from tests.api.test_analysis import RC, zipped
from tests.api.test_bids import deposit, new_bid
from tests.api.test_consultations import SERVICES
from tests.api.test_exports import FakeConverter
from tests.api.test_pricing import LINES, credits_left, read
from tests.conftest import FakeQueue, MemoryStorage, Outbox
from tests.documents_helpers import make_pdf
from tests.domain.test_pricing import rillieux_like

Factory = Callable[[], TestClient]
YEAR = datetime.now(ZoneInfo("Europe/Paris")).year

CCTP = make_pdf(
    [
        ["Prestation quotidienne des gymnases : nettoyage des sols,",
         "vidage des corbeilles et entretien des sanitaires."],
        ["Interventions de nuit : remise en etat apres manifestation."],
        ["Peinture acrylique mate des plafonds."],
    ]
)  # fmt: skip


class Model:
    """Reads the price file, matches the price list, then writes « Prestations comprises »."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.error: Exception | None = None

    def __call__(
        self, model: str, messages: list[dict[str, Any]], max_tokens: int | None = None
    ) -> tuple[str, int, int, float]:
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        reply: dict[str, Any]
        if "<passages>" in prompt:
            if self.error is not None:
                raise self.error
            reply = {"inclusions": [
                {"text": "Nettoyage des sols des gymnases.", "file": "CCTP.pdf", "page": 1},
                {"text": "Peinture des plafonds.", "file": "CCTP.pdf", "page": 3},  # not sent
            ]}  # fmt: skip
        elif "<services>" in prompt:
            first = next(ln for ln in prompt.splitlines() if "Nettoyage quotidien" in ln)
            sid = first.split(" · ")[0].strip()
            reply = {"matches": [{"line": "DQE!B5", "service": sid},
                                 {"line": "DQE!B6", "service": sid}]}  # fmt: skip
        else:
            reply = {"lines": LINES, "notes": []}
        return json.dumps(reply), 800, 200, 0.001

    def passages(self) -> list[str]:
        return [p for p in self.prompts if "<passages>" in p]


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> Model:
    fake = Model()
    for name in ("llm_model_extraction", "llm_model_generation"):
        monkeypatch.setattr(get_settings(), name, f"test/{name}")
    monkeypatch.setattr(llm, "_call_provider", fake)
    return fake


@pytest.fixture
def converter() -> FakeConverter:
    return FakeConverter()


def consultation(
    c: TestClient, queue: FakeQueue, *, cctp: bool = True, kind: str = "consultation"
) -> str:
    files = {"DCE/RC.pdf": RC, "DCE/26020M_DQE.xlsx": rillieux_like()}
    if cctp:
        files["DCE/CCTP.pdf"] = CCTP
    bid = new_bid(
        c,
        kind=kind,
        title="Gymnases — nettoyage",
        contact_name="Mme Exemple",
        contact_email="contact@eg-exemple.fr",
    )
    assert deposit(c, bid, ("DCE.zip", zipped(files))).status_code == 202
    queue.drain_dce()
    return bid


def quote_state(c: TestClient, bid: str) -> dict[str, Any]:
    res = c.get(f"/bids/{bid}/quote")
    assert res.status_code == 200, res.text
    return dict(res.json())


def downloaded(c: TestClient, storage: MemoryStorage, bid: str, fmt: str) -> bytes:
    res = c.post(f"/bids/{bid}/quote/download", json={"format": fmt})
    assert res.status_code == 200, res.text
    key = res.json()["url"].split("https://storage.test/")[1].split("?")[0]
    return storage.objects[key]


def docx_text(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    parts += [" | ".join(c.text for c in row.cells) for t in doc.tables for row in t.rows]
    return "\n".join(parts)


def test_a_quote_is_numbered_sourced_and_charged_once(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    storage: MemoryStorage,
    model: Model,
    converter: FakeConverter,
) -> None:
    c = signed_in_client(make_client, outbox)
    c.put("/profile/services", json={"services": SERVICES})
    bid = consultation(c, queue)
    read(c, queue, bid)
    state = quote_state(c, bid)
    assert state["quote"] is None and state["blocking"] is None and state["cctp"] is True

    before = credits_left(c)
    res = c.post(f"/bids/{bid}/quote", json={})
    assert res.status_code == 202, res.text
    assert res.json()["number"] == f"D-{YEAR}-0001" and res.json()["status"] == "drafting"
    assert c.post(f"/bids/{bid}/quote", json={}).status_code == 202  # a second click: same work
    assert credits_left(c) == before - 1
    queue.drain_quotes(converter)

    quote = quote_state(c, bid)["quote"]
    assert quote["status"] == "ready" and quote["has_pdf"] and quote["has_docx"]
    assert quote["inclusions"] == [
        {"text": "Nettoyage des sols des gymnases.", "file": "CCTP.pdf", "page": 1}
    ]  # the bullet citing a page that was not sent is dropped
    sent = model.passages()
    assert len(sent) == 1 and "[CCTP.pdf p.1]" in sent[0] and "Peinture" not in sent[0]
    ht = 9000 * 208 + 9000 * 188
    assert (quote["total_ht_cents"], quote["vat_cents"]) == (ht, ht // 5)
    assert quote["total_ttc_cents"] == ht + ht // 5
    text = docx_text(downloaded(c, storage, bid, "docx"))
    assert f"Devis n° D-{YEAR}-0001" in text and "Mme Exemple — contact@eg-exemple.fr" in text
    assert "Gymnase A | jour | 208 | 90,00 € | 18 720,00 €" in text
    assert "Nettoyage des sols des gymnases. (CCTP.pdf, p. 1)" in text
    assert "Interventions" not in text and "Nuit" not in text  # the rubriques set aside
    assert downloaded(c, storage, bid, "pdf").startswith(b"%PDF")

    # the settings change, the quote is rebuilt for free, the bullets are the company's
    res = c.put(
        f"/bids/{bid}/quote",
        json={"validity_days": 45, "vat_bp": 1000, "inclusions": [{"text": "Mon texte"}]},
    )
    assert res.status_code == 200, res.text
    queue.drain_quotes(converter)
    quote = quote_state(c, bid)["quote"]
    assert quote["status"] == "ready" and quote["validity_days"] == 45
    assert quote["inclusions"] == [{"text": "Mon texte", "file": None, "page": None}]
    assert credits_left(c) == before - 1 and len(model.passages()) == 1
    text = docx_text(downloaded(c, storage, bid, "docx"))
    assert "valable 45 jours" in text and "TVA 10 %" in text and "Mon texte" in text

    # the bundle: the quote and the client's file filled with the lines priced
    names = zipfile.ZipFile(io.BytesIO(downloaded(c, storage, bid, "zip"))).namelist()
    assert sorted(names) == ["26020M_DQE - rempli.xlsx", f"Devis D-{YEAR}-0001.docx",
                             f"Devis D-{YEAR}-0001.pdf"]  # fmt: skip

    # the next consultation takes the next number
    other = consultation(c, queue)
    read(c, queue, other)
    assert c.post(f"/bids/{other}/quote", json={}).json()["number"] == f"D-{YEAR}-0002"


def test_a_quote_waits_for_every_price(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = consultation(c, queue)
    assert c.post(f"/bids/{bid}/quote", json={}).status_code == 409  # nothing read yet
    read(c, queue, bid)  # no price list: the four lines are to price
    state = quote_state(c, bid)
    assert state["blocking"] == "Il reste 4 prix à saisir dans l'onglet Prix."
    res = c.post(f"/bids/{bid}/quote", json={})
    assert res.status_code == 409 and res.json()["error"]["code"] == "prices_missing"


def test_a_tender_has_no_quote(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model
) -> None:
    c = signed_in_client(make_client, outbox)
    c.put("/profile/services", json={"services": SERVICES})
    bid = consultation(c, queue, kind="tender")
    assert c.post(f"/bids/{bid}/quote", json={}).status_code == 422


def test_without_cctp_the_quote_is_free_and_writes_no_bullet(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: Model,
    converter: FakeConverter,
) -> None:
    c = signed_in_client(make_client, outbox)
    c.put("/profile/services", json={"services": SERVICES})
    bid = consultation(c, queue, cctp=False)
    read(c, queue, bid)
    before = credits_left(c)
    assert quote_state(c, bid)["cctp"] is False
    assert c.post(f"/bids/{bid}/quote", json={}).status_code == 202
    queue.drain_quotes(converter)
    quote = quote_state(c, bid)["quote"]
    assert quote["status"] == "ready" and quote["inclusions"] == []
    assert credits_left(c) == before and model.passages() == []


def test_a_failed_quote_gives_the_credit_back(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: Model,
    converter: FakeConverter,
) -> None:
    c = signed_in_client(make_client, outbox)
    c.put("/profile/services", json={"services": SERVICES})
    bid = consultation(c, queue)
    read(c, queue, bid)
    before = credits_left(c)
    model.error = llm.LlmProviderError("down")
    c.post(f"/bids/{bid}/quote", json={})
    queue.drain_quotes(converter)
    quote = quote_state(c, bid)["quote"]
    assert quote["status"] == "error" and quote["error"]
    assert credits_left(c) == before
    assert c.post(f"/bids/{bid}/quote/download", json={"format": "pdf"}).status_code == 409


def test_a_pdf_that_cannot_be_made_leaves_the_word_file(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: Model,
    converter: FakeConverter,
) -> None:
    from app.exports.pdf import PdfUnavailable

    c = signed_in_client(make_client, outbox)
    c.put("/profile/services", json={"services": SERVICES})
    bid = consultation(c, queue, cctp=False)
    read(c, queue, bid)
    converter.error = PdfUnavailable("LibreOffice absent")
    c.post(f"/bids/{bid}/quote", json={})
    queue.drain_quotes(converter)
    quote = quote_state(c, bid)["quote"]
    assert quote["status"] == "ready" and quote["has_docx"] and not quote["has_pdf"]
    assert c.post(f"/bids/{bid}/quote/download", json={"format": "pdf"}).status_code == 409


def test_bad_settings_are_refused(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model, converter: FakeConverter
) -> None:
    c = signed_in_client(make_client, outbox)
    c.put("/profile/services", json={"services": SERVICES})
    bid = consultation(c, queue, cctp=False)
    read(c, queue, bid)
    assert c.put(f"/bids/{bid}/quote", json={"validity_days": 30}).status_code == 404  # no quote
    c.post(f"/bids/{bid}/quote", json={})
    queue.drain_quotes(converter)
    for bad in ({"validity_days": 0}, {"vat_bp": 10001}, {"inclusions": [{"text": ""}]}):
        assert c.put(f"/bids/{bid}/quote", json=bad).status_code == 422, bad


def test_another_company_sees_no_quote(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model, converter: FakeConverter
) -> None:
    a = signed_in_client(make_client, outbox, 1)
    a.put("/profile/services", json={"services": SERVICES})
    bid = consultation(a, queue, cctp=False)
    read(a, queue, bid)
    a.post(f"/bids/{bid}/quote", json={})
    b = signed_in_client(make_client, outbox, 2)
    assert b.get(f"/bids/{bid}/quote").status_code == 404
    assert b.post(f"/bids/{bid}/quote/download", json={"format": "docx"}).status_code == 404


def test_a_dead_quote_is_closed_and_refunded(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: Model, db: Session
) -> None:
    from sqlalchemy import update

    from app.db.models import Quote
    from app.services.stale_works import sweep_stale_works

    c = signed_in_client(make_client, outbox)
    c.put("/profile/services", json={"services": SERVICES})
    bid = consultation(c, queue)
    read(c, queue, bid)
    before = credits_left(c)
    c.post(f"/bids/{bid}/quote", json={})
    assert credits_left(c) == before - 1
    db.execute(update(Quote).values(updated_at=datetime.now(UTC) - timedelta(hours=2)))
    db.commit()
    assert sweep_stale_works(db, queue) == 1
    assert quote_state(c, bid)["quote"]["status"] == "error"
    assert credits_left(c) == before
