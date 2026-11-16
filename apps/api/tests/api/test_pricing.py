"""Chiffrage (ADR-049): rates, reading the price file, typing hours, the filled file."""

import io
import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import llm
from app.core.config import get_settings
from app.db.models import File, PriceSheet
from tests.api.helpers import signed_in_client
from tests.api.test_analysis import RC, zipped
from tests.api.test_bids import deposit, new_bid
from tests.conftest import FakeQueue, MemoryStorage, Outbox
from tests.domain.test_pricing import rillieux_like

Factory = Callable[[], TestClient]

LINES = [
    {"sheet": "DQE", "section": "prestation quotidienne", "label": "Gymnase A", "unit": "jour",
     "quantity_cell": "I5", "price_cell": "B5", "hours_cell": "C5", "rate_cell": "D5"},
    {"sheet": "DQE", "section": "prestation quotidienne", "label": "Gymnase B", "unit": "jour",
     "quantity_cell": "I6", "price_cell": "B6", "hours_cell": "C6", "rate_cell": "D6"},
    {"sheet": "DQE", "section": "prestation annuelle", "label": "Gymnase A", "unit": "jour",
     "quantity_cell": "I32", "price_cell": "B32"},
    {"sheet": "DQE", "section": "interventions", "label": "Nuit (21h-6h)", "unit": "heure",
     "quantity_cell": "I42", "price_cell": "B42", "hourly": True, "surcharge": "night"},
]  # fmt: skip


class PriceModel:
    def __init__(self) -> None:
        self.lines: list[dict[str, Any]] = LINES
        self.error: Exception | None = None
        self.prompts: list[str] = []

    def __call__(
        self, model: str, messages: list[dict[str, Any]], max_tokens: int | None = None
    ) -> tuple[str, int, int, float]:
        if self.error is not None:
            raise self.error
        self.prompts.append(messages[-1]["content"])
        reply = {"lines": self.lines, "notes": ["Prix en euros HT"]}
        return json.dumps(reply), 1000, 300, 0.002


@pytest.fixture
def reader(monkeypatch: pytest.MonkeyPatch) -> PriceModel:
    fake = PriceModel()
    monkeypatch.setattr(get_settings(), "llm_model_extraction", "test/extraction")
    monkeypatch.setattr(llm, "_call_provider", fake)
    return fake


def bid_with_prices(c: TestClient, queue: FakeQueue, *, pdf_twin: bool = True) -> str:
    files = {"DCE/RC.pdf": RC, "DCE/26020M_DQE.xlsx": rillieux_like()}
    if pdf_twin:
        files["DCE/26020M_DQE.pdf"] = RC  # the same table printed: hidden behind the Excel
    bid = new_bid(c)
    assert deposit(c, bid, ("DCE.zip", zipped(files))).status_code == 202
    queue.drain_dce()
    return bid


def prices(c: TestClient, bid: str) -> dict[str, Any]:
    res = c.get(f"/bids/{bid}/prices")
    assert res.status_code == 200, res.text
    return dict(res.json())


def credits_left(c: TestClient) -> int:
    return int(c.get("/credits").json()["total"])


def read(c: TestClient, queue: FakeQueue, bid: str) -> dict[str, Any]:
    file_id = prices(c, bid)["files"][0]["dce_file_id"]
    res = c.post(f"/bids/{bid}/prices/{file_id}/read")
    assert res.status_code == 202, res.text
    queue.drain_price_reads()
    sheet = prices(c, bid)["files"][0]["sheet"]
    assert sheet is not None
    return dict(sheet)


def test_rates_saved_and_read(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    empty = c.get("/profile/rates").json()
    assert empty == {
        "hourly_rate_cents": None,
        "night_pct": None,
        "sunday_pct": None,
        "holiday_pct": None,
    }
    body = {"hourly_rate_cents": 2500, "night_pct": 25, "sunday_pct": None, "holiday_pct": 100}
    assert c.put("/profile/rates", json=body).json() == body
    assert c.get("/profile/rates").json() == body
    assert c.put("/profile/rates", json={"hourly_rate_cents": 0}).status_code == 422


def test_read_type_hours_and_download_the_filled_file(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    reader: PriceModel,
    storage: MemoryStorage,
    db: Session,
) -> None:
    c = signed_in_client(make_client, outbox)
    c.put("/profile/rates", json={"hourly_rate_cents": 2500, "night_pct": 25})
    bid = bid_with_prices(c, queue)
    listed = prices(c, bid)
    assert [f["path"] for f in listed["files"]] == ["DCE/26020M_DQE.xlsx"]  # PDF twin hidden
    assert listed["files"][0]["fillable"] and listed["files"][0]["sheet"] is None
    before = credits_left(c)
    sheet = read(c, queue, bid)
    assert credits_left(c) == before - 1
    assert sheet["status"] == "ready" and sheet["notes"] == ["Prix en euros HT"]
    assert [ln["label"] for ln in sheet["lines"]] == [
        "Gymnase A",
        "Gymnase B",
        "Gymnase A",
        "Nuit (21h-6h)",
    ]
    assert any("H32" in w for w in sheet["warnings"])  # the broken link of the yearly table
    assert "B5: 0" in reader.prompts[0] and "H5: =B5" in reader.prompts[0]
    night = sheet["lines"][3]
    assert night["price_cents"] == 3125 and night["source"] == "hourly"  # 25 € + 25 %
    assert sheet["missing_count"] == 3

    res = c.put(
        f"/price-sheets/{sheet['id']}",
        json={"entries": {"DQE!B5": {"hours": "2,5"}, "DQE!B32": {"price_cents": 40000}}},
    )
    assert res.status_code == 200, res.text
    out = res.json()
    first = out["lines"][0]
    assert (first["hours"], first["price_cents"], first["total_cents"]) == ("2.5", 6250, 1300000)
    assert out["missing_count"] == 1  # Gymnase B still has nothing
    assert out["total_cents"] == 6250 * 208 + 40000 * 2 + 3125 * 2

    link = c.post(f"/price-sheets/{sheet['id']}/export")
    assert link.status_code == 200, link.text
    key = link.json()["url"].split("https://storage.test/")[1].split("?")[0]
    ws = load_workbook(io.BytesIO(storage.objects[key]))["DQE"]
    assert (ws["B5"].value, ws["C5"].value, ws["D5"].value) == (62.5, 2.5, 25)
    assert ws["B32"].value == 400 and ws["H32"].value == 400  # the broken link repaired
    assert ws["B6"].value == 0  # missing: left as the buyer gave it
    assert ws["H5"].value == "=B5" and ws["J47"].value == "=SUM(J5:J42)"
    files = db.scalar(select(func.count()).select_from(File))
    assert c.post(f"/price-sheets/{sheet['id']}/export").status_code == 200
    assert db.scalar(select(func.count()).select_from(File)) == files  # the old copy is gone


def test_dossier_rate_replaces_the_company_rate(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: PriceModel
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = bid_with_prices(c, queue)
    sheet = read(c, queue, bid)
    out = c.put(
        f"/price-sheets/{sheet['id']}",
        json={"entries": {"DQE!B5": {"hours": "2"}}, "rate_cents": 3000, "set_rate": True},
    ).json()
    assert out["rate_cents"] == 3000 and out["lines"][0]["price_cents"] == 6000
    cleared = c.put(f"/price-sheets/{sheet['id']}", json={"set_rate": True}).json()
    assert cleared["rate_cents"] is None and cleared["lines"][0]["price_cents"] is None


def test_bad_entries_refused(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: PriceModel
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = bid_with_prices(c, queue)
    sheet = read(c, queue, bid)
    url = f"/price-sheets/{sheet['id']}"
    unknown = c.put(url, json={"entries": {"DQE!Z9": {"hours": "1"}}})
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "unknown_line"
    for hours in ("abc", "-2", "0"):
        bad = c.put(url, json={"entries": {"DQE!B5": {"hours": hours}}})
        assert bad.status_code == 422, hours
    assert c.put(url, json={"entries": {"DQE!B5": {"price_cents": -1}}}).status_code == 422


def test_pdf_alone_cannot_be_filled(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: PriceModel
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    deposit(c, bid, ("DCE.zip", zipped({"DCE/RC.pdf": RC, "DCE/DPGF.pdf": RC})))
    queue.drain_dce()
    listed = prices(c, bid)["files"]
    assert [(f["path"], f["fillable"]) for f in listed] == [("DCE/DPGF.pdf", False)]
    before = credits_left(c)
    res = c.post(f"/bids/{bid}/prices/{listed[0]['dce_file_id']}/read")
    assert res.status_code == 422 and res.json()["error"]["code"] == "not_fillable"
    assert credits_left(c) == before


def test_failed_reading_gives_the_credit_back(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: PriceModel
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = bid_with_prices(c, queue)
    before = credits_left(c)
    reader.error = RuntimeError("provider down")
    sheet = read(c, queue, bid)
    assert sheet["status"] == "error" and "indisponible" in sheet["error"]
    assert credits_left(c) == before
    reader.error = None
    reader.lines = [{**LINES[0], "price_cell": "H5"}]  # only a formula: nothing to fill
    sheet = read(c, queue, bid)
    assert sheet["status"] == "error" and "aucune ligne" in sheet["error"]
    assert credits_left(c) == before
    assert c.post(f"/price-sheets/{sheet['id']}/export").status_code == 409


def test_second_click_is_not_charged_twice(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: PriceModel, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = bid_with_prices(c, queue)
    file_id = prices(c, bid)["files"][0]["dce_file_id"]
    before = credits_left(c)
    assert c.post(f"/bids/{bid}/prices/{file_id}/read").status_code == 202
    assert c.post(f"/bids/{bid}/prices/{file_id}/read").status_code == 202
    assert credits_left(c) == before - 1 and len(queue.pending_price_reads) == 1
    assert db.scalar(select(func.count()).select_from(PriceSheet)) == 1


def test_entries_kept_when_read_again(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: PriceModel
) -> None:
    c = signed_in_client(make_client, outbox)
    c.put("/profile/rates", json={"hourly_rate_cents": 2000})
    bid = bid_with_prices(c, queue)
    sheet = read(c, queue, bid)
    c.put(f"/price-sheets/{sheet['id']}", json={"entries": {"DQE!B5": {"hours": "3"}}})
    reader.lines = LINES[:1]  # the new reading finds only the first line
    again = read(c, queue, bid)
    assert again["id"] == sheet["id"] and len(again["lines"]) == 1
    assert again["lines"][0]["price_cents"] == 6000


def test_other_company_sees_nothing(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: PriceModel
) -> None:
    a = signed_in_client(make_client, outbox, 1)
    bid = bid_with_prices(a, queue)
    sheet = read(a, queue, bid)
    b = signed_in_client(make_client, outbox, 2)
    assert b.get(f"/bids/{bid}/prices").status_code == 404
    assert b.put(f"/price-sheets/{sheet['id']}", json={}).status_code == 404
    assert b.post(f"/price-sheets/{sheet['id']}/export").status_code == 404


def test_a_dead_reading_is_closed_refunded_and_a_new_one_can_start(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: PriceModel, db: Session
) -> None:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.services.stale_works import sweep_stale_works

    c = signed_in_client(make_client, outbox)
    bid = bid_with_prices(c, queue)
    file_id = prices(c, bid)["files"][0]["dce_file_id"]
    before = credits_left(c)
    assert c.post(f"/bids/{bid}/prices/{file_id}/read").status_code == 202
    queue.pending_price_reads.clear()  # the worker died with it
    db.execute(update(PriceSheet).values(updated_at=datetime.now(UTC) - timedelta(minutes=20)))
    db.commit()
    assert sweep_stale_works(db, queue) == 1
    sheet = prices(c, bid)["files"][0]["sheet"]
    assert sheet["status"] == "error" and "interrompue" in sheet["error"]
    assert credits_left(c) == before
    assert read(c, queue, bid)["status"] == "ready"


def test_typed_hours_reach_the_memoir_never_the_prices(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: PriceModel, db: Session
) -> None:
    import uuid

    from app.db.models import Bid, Organization
    from app.services.memoir_drafting import company_data_for_bid

    c = signed_in_client(make_client, outbox)
    c.put("/profile/rates", json={"hourly_rate_cents": 2500})
    bid_id = bid_with_prices(c, queue)
    sheet = read(c, queue, bid_id)
    bid = db.get_one(Bid, uuid.UUID(bid_id))
    org = db.get_one(Organization, bid.org_id)
    assert "dossier_hours" not in company_data_for_bid(db, org, bid)
    c.put(f"/price-sheets/{sheet['id']}", json={"entries": {"DQE!B5": {"hours": "2.5"}}})
    db.expire_all()
    data = company_data_for_bid(db, org, bid)
    assert data["dossier_hours"]["heures_totales"] == "520"
    assert data["dossier_hours"]["lignes"][0]["libelle"] == "Gymnase A"
    assert "6250" not in json.dumps(data) and "62.5" not in json.dumps(data)


def test_the_same_line_in_the_other_price_file_follows(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: PriceModel
) -> None:
    """Rillieux: the BPM and the DQE hold the same lines and must carry the same prices; what
    is typed in one goes to the same line of the other (same section, same label)."""
    c = signed_in_client(make_client, outbox)
    c.put("/profile/rates", json={"hourly_rate_cents": 2500})
    files = {
        "DCE/RC.pdf": RC,
        "DCE/26020M_DQE.xlsx": rillieux_like(),
        "DCE/BPM.xlsx": rillieux_like(),
    }
    bid = new_bid(c)
    deposit(c, bid, ("DCE.zip", zipped(files)))
    queue.drain_dce()
    listed = prices(c, bid)["files"]
    assert sorted(f["path"] for f in listed) == ["DCE/26020M_DQE.xlsx", "DCE/BPM.xlsx"]
    first, second = listed
    c.post(f"/bids/{bid}/prices/{first['dce_file_id']}/read")
    queue.drain_price_reads()
    sheet = next(
        f["sheet"] for f in prices(c, bid)["files"] if f["dce_file_id"] == first["dce_file_id"]
    )
    c.put(f"/price-sheets/{sheet['id']}", json={"entries": {"DQE!B5": {"hours": "3"}}})
    # read later: the second file starts with what was typed in the first
    c.post(f"/bids/{bid}/prices/{second['dce_file_id']}/read")
    queue.drain_price_reads()
    other = next(
        f["sheet"] for f in prices(c, bid)["files"] if f["dce_file_id"] == second["dce_file_id"]
    )
    assert other["lines"][0]["hours"] == "3" and other["lines"][0]["price_cents"] == 7500
    assert any("repris" in w for w in other["warnings"])
    # typed afterwards in the second: the first follows
    c.put(f"/price-sheets/{other['id']}", json={"entries": {"DQE!B6": {"price_cents": 9000}}})
    again = next(
        f["sheet"] for f in prices(c, bid)["files"] if f["dce_file_id"] == first["dce_file_id"]
    )
    assert again["lines"][1]["price_cents"] == 9000


def test_an_option_is_shown_apart_from_the_total(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: PriceModel
) -> None:
    """A PSE or « OPTION : … » line: priced and written, but the offer's total leaves it out."""
    c = signed_in_client(make_client, outbox)
    c.put("/profile/rates", json={"hourly_rate_cents": 2500, "night_pct": 25})
    reader.lines = [dict(ln) for ln in LINES]
    reader.lines[2]["option"] = True  # the yearly service, as a PSE
    sheet = read(c, queue, bid_with_prices(c, queue))
    assert [ln["option"] for ln in sheet["lines"]] == [False, False, True, False]
    res = c.put(
        f"/price-sheets/{sheet['id']}",
        json={"entries": {"DQE!B5": {"hours": "2,5"}, "DQE!B32": {"price_cents": 40000}}},
    )
    out = res.json()
    assert out["total_cents"] == 6250 * 208 + 3125 * 2
    assert out["options_total_cents"] == 40000 * 2
    assert out["lines"][2]["total_cents"] == 40000 * 2
