"""A DCE deposited in several goes (« pièce oubliée »), the analysis on the user's go, and a file
Pilao cannot read that no longer blocks the deposit (ENG PRO, 23/11: AWS DCE in several ZIPs)."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DceFile, DceVersion
from tests.api.helpers import signed_in_client
from tests.api.test_bids import CCTP_V1, RC, Factory, new_bid, zipped
from tests.conftest import FakeQueue, FakeScanner, Outbox

BPU = zipped({"BPU.pdf": RC})


def send(c: TestClient, bid_id: str, *files: tuple[str, bytes], **params: str) -> Any:
    return c.post(
        f"/bids/{bid_id}/dce",
        params=params,
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
    )


def version(c: TestClient, bid_id: str, n: int = 1) -> dict[str, Any]:
    return c.get(f"/bids/{bid_id}/dce/{n}").json()  # type: ignore[no-any-return]


def names(v: dict[str, Any]) -> list[str]:
    return sorted(f["path"] for f in v["files"])


def test_a_file_pilao_cannot_read_no_longer_blocks_the_deposit(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    res = send(c, bid, ("RC.pdf", RC), ("notes.txt", b"bonjour"))
    assert res.status_code == 202, res.text
    queue.drain_dce()
    v = version(c, bid)
    assert v["status"] == "ready" and names(v) == ["RC.pdf"]
    assert {"path": "notes.txt", "reason": "format non lu par Pilao"} in [
        {"path": s["path"], "reason": s["reason"]} for s in v["skipped"]
    ]
    # nothing readable at all: still refused
    assert send(c, new_bid(c), ("notes.txt", b"bonjour")).status_code == 415


def test_a_manual_deposit_waits_for_the_go_of_the_analysis(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    assert send(c, bid, ("RC.pdf", RC), analyse="false").status_code == 202
    queue.drain_dce()
    assert version(c, bid)["status"] == "ready"
    assert queue.pending_analyses == []
    assert c.get(f"/bids/{bid}/analysis").status_code == 404  # waits for « Lancer l'analyse »
    assert c.post(f"/bids/{bid}/analysis").status_code == 202
    assert len(queue.pending_analyses) == 1


def test_forgotten_pieces_complete_the_current_version(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    send(c, bid, ("RC.pdf", RC), analyse="false")
    queue.drain_dce()
    first = version(c, bid)
    rc_id = first["files"][0]["id"]
    assert first["completed_at"] is None

    res = send(c, bid, ("CCTP.pdf", CCTP_V1), ("Pieces.zip", BPU), mode="add")
    assert res.status_code == 202, res.text
    assert res.json()["version"] == 1  # the same version, completed
    queue.drain_dce()
    v = version(c, bid)
    assert v["status"] == "ready" and names(v) == ["BPU.pdf", "CCTP.pdf", "RC.pdf"]
    assert v["completed_at"] is not None
    assert rc_id in [f["id"] for f in v["files"]]  # the pieces already read keep their identity
    assert [x["version"] for x in c.get(f"/bids/{bid}/dce").json()] == [1]
    assert queue.pending_analyses == []  # never analysed by itself after an addition

    # the same piece added again is reported, not duplicated
    send(c, bid, ("RC.pdf", RC), mode="add")
    queue.drain_dce()
    v = version(c, bid)
    assert names(v) == ["BPU.pdf", "CCTP.pdf", "RC.pdf"]
    assert any(s["reason"] == "doublon d'un fichier déjà déposé" for s in v["skipped"])
    rows = db.scalars(select(DceFile).where(DceFile.dce_version_id == uuid.UUID(v["id"])))
    assert len(rows.all()) == 3


def test_adding_needs_a_ready_dce(make_client: Factory, outbox: Outbox, queue: FakeQueue) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    res = send(c, bid, ("RC.pdf", RC), mode="add")
    assert res.status_code == 409 and res.json()["error"]["code"] == "no_dce"
    send(c, bid, ("RC.pdf", RC))
    res = send(c, bid, ("CCTP.pdf", CCTP_V1), mode="add")
    assert res.status_code == 409 and res.json()["error"]["code"] == "dce_processing"
    assert send(c, bid, ("RC.pdf", RC), mode="autre").status_code == 422


def test_an_unusable_addition_keeps_the_version_ready(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    send(c, bid, ("RC.pdf", RC))
    queue.drain_dce()
    send(c, bid, ("plans.zip", zipped({"plan.dwg": b"AC1027"})), mode="add")
    queue.drain_dce()
    v = version(c, bid)
    assert v["status"] == "ready" and v["error"] is None and names(v) == ["RC.pdf"]
    assert any(s["path"].endswith("plan.dwg") for s in v["skipped"])


def test_an_interrupted_addition_is_retried_without_duplicates(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scanner: FakeScanner, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    send(c, bid, ("RC.pdf", RC))
    queue.drain_dce()
    res = send(c, bid, ("Pieces.zip", zipped({"CCTP.pdf": CCTP_V1, "BPU.pdf": RC})), mode="add")
    scanner.down = True
    with pytest.raises(Exception):  # noqa: B017 - the worker re-raises so that RQ retries
        queue.drain_dce()
    scanner.down = False
    queue.pending_dce.append(uuid.UUID(res.json()["id"]))
    queue.drain_dce()
    v = version(c, bid)
    assert v["status"] == "ready" and names(v) == ["BPU.pdf", "CCTP.pdf", "RC.pdf"]
    version_id = db.scalars(select(DceVersion.id).where(DceVersion.bid_id == uuid.UUID(bid))).one()
    assert len(db.scalars(select(DceFile).where(DceFile.dce_version_id == version_id)).all()) == 3


def test_a_whole_dce_folder_fits_in_one_deposit(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    files = [(f"piece-{i}.pdf", RC + str(i).encode()) for i in range(60)]
    assert send(c, new_bid(c), *files).status_code == 202  # was 50 files at most
