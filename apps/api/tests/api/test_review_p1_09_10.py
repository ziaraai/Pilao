"""Regression tests for the review of P1-09 / P1-10 and the decisions taken after it."""

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.ai import llm
from app.db.models import DceAnalysis, DceVersion
from app.domain.go_no_go import VaultEntry, check_documents
from app.schemas.dce_analysis import DceAnalysisData
from app.services.dce_analysis import SCOPE_REQUIREMENTS, Doc, plan_calls, verify
from tests.api.helpers import signed_in_client
from tests.api.test_analysis import DCE, DEADLINE, SRC_RC, FakeModel, install_fake_model
from tests.api.test_bids import CCTP_V1, RC, deposit, new_bid, zipped
from tests.conftest import FakeQueue, FakeScanner, Outbox

Factory = Callable[[], TestClient]


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    return install_fake_model(monkeypatch)


# ---------- decisions ---------------------------------------------------------------------


def test_file_too_large_for_the_antivirus_is_a_clear_413(
    make_client: Factory, outbox: Outbox, scanner: FakeScanner
) -> None:
    c = signed_in_client(make_client, outbox)
    scanner.too_large = True
    res = c.post("/files", files={"file": ("plan.pdf", b"%PDF-1.4 plan", "application/pdf")})
    assert res.status_code == 413 and res.json()["error"]["code"] == "too_large_for_scan"


def test_dce_waiting_for_retry_blocks_a_new_deposit_until_stale(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scanner: FakeScanner, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    deposit(c, bid, ("RC.pdf", RC))
    scanner.down = True
    with pytest.raises(Exception):  # noqa: B017 - re-raised for RQ
        queue.drain_dce()
    scanner.down = False
    version = c.get(f"/bids/{bid}/dce/1").json()
    assert version["status"] == "processing" and "nouvelle tentative" in version["error"]
    assert deposit(c, bid, ("RC.pdf", RC)).json()["error"]["code"] == "dce_processing"
    # The retries never came (worker killed): after twice the job timeout, deposits reopen.
    db.execute(update(DceVersion).values(updated_at=datetime.now(UTC) - timedelta(hours=2)))
    db.commit()
    assert deposit(c, bid, ("RC.pdf", RC)).status_code == 202


def test_analysis_waiting_for_retry_blocks_a_rerun_until_stale(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: FakeModel,
    db: Session,
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    deposit(c, bid, DCE)
    queue.drain_dce()
    model.error = llm.LlmProviderError("down")
    with pytest.raises(llm.LlmProviderError):
        queue.drain_analyses()
    assert c.get(f"/bids/{bid}/analysis").json()["status"] == "processing"
    assert c.post(f"/bids/{bid}/analysis").json()["error"]["code"] == "analysis_running"
    db.execute(update(DceAnalysis).values(updated_at=datetime.now(UTC) - timedelta(hours=2)))
    db.commit()
    assert c.post(f"/bids/{bid}/analysis").status_code == 202


def test_go_no_go_uses_the_deadline_corrected_on_the_bid(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, model: FakeModel
) -> None:
    c = signed_in_client(make_client, outbox)
    soon = (datetime.now(UTC) + timedelta(days=5)).isoformat()  # amendment: deadline moved earlier
    bid = c.post("/bids", json={"title": "Nettoyage", "deadline_at": soon}).json()["id"]
    deposit(c, bid, DCE)  # the DCE still says +30 days
    queue.drain_dce()
    queue.drain_analyses()
    factors = {f["label"]: f for f in c.get(f"/bids/{bid}/analysis").json()["go_no_go"]["factors"]}
    assert factors["Délai"]["status"] == "warning" and "serré" in factors["Délai"]["detail"]


# ---------- review findings ---------------------------------------------------------------


def test_the_longest_valid_attestation_is_used() -> None:
    vault = [
        VaultEntry("urssaf_vigilance", "valid", date(2026, 11, 20)),  # old one kept in the vault
        VaultEntry("urssaf_vigilance", "valid", date(2027, 5, 1)),  # renewed
    ]
    (check,) = check_documents([("Attestation URSSAF", "candidature", None)], vault, DEADLINE)
    assert check.status == "available"


def test_unsourced_visit_and_memoir_details_are_cleared() -> None:
    rc = Doc(uuid.uuid4(), SRC_RC, "rc", True, [(1, "x")])
    data = DceAnalysisData.model_validate(
        {
            "site_visit": {
                "mandatory": None,
                "dates": [],
                "details": "Visite le lundi",
                "source": None,
            },
            "memoir_requirements": {
                "imposed_outline": [],
                "max_pages": None,
                "format_constraints": "Arial 11",
                "response_template_provided": True,
                "source": {"file": "nulle-part.pdf", "page": 1},
            },
        }
    )
    out, warnings = verify(data, [rc])
    assert out["site_visit"]["details"] is None and out["site_visit"]["source"] is None
    assert out["memoir_requirements"]["format_constraints"] is None
    assert out["memoir_requirements"]["response_template_provided"] is None and warnings


def test_one_bad_lot_does_not_fail_the_analysis() -> None:
    data = DceAnalysisData.model_validate(
        {
            "key_info": {
                "lots": [{"number": 1}, {"title": "Lot 2", "source": {"file": SRC_RC, "page": 1}}]
            }
        }
    )
    assert [lot.title for lot in data.key_info.lots] == ["Lot 2"]


def test_an_oversized_cctp_alone_sends_no_empty_call() -> None:
    cctp = Doc(uuid.uuid4(), "CCTP.pdf", "cctp", True, [(i, "x" * 400) for i in range(1, 5)])
    calls, _ = plan_calls([cctp], budget=1000, max_calls=8)
    assert calls and all(c.scope.startswith(SCOPE_REQUIREMENTS.split("{")[0]) for c in calls)
    assert all("CCTP.pdf" in c.documents for c in calls)


def test_a_piece_that_cannot_fit_at_all_is_named() -> None:
    huge = Doc(uuid.uuid4(), "Annexe.pdf", "annex", True, [(1, "y" * 5000)])
    rc = Doc(uuid.uuid4(), "RC.pdf", "rc", True, [(1, "x" * 900)])
    _, warnings = plan_calls([rc, huge], budget=1000, max_calls=8)
    assert any("Annexe.pdf" in w and "n'a pas pu être analysé" in w for w in warnings)


def test_duplicate_paths_identical_skipped_different_kept(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    res = deposit(
        c,
        bid,
        ("lot1.zip", zipped({"RC.pdf": RC})),
        ("lot1_copie.zip", zipped({"RC.pdf": RC})),  # same path, same content
        ("lot2.zip", zipped({"RC.pdf": CCTP_V1})),  # same path, different content
    )
    assert res.status_code == 202
    queue.drain_dce()
    version = c.get(f"/bids/{bid}/dce/1").json()
    assert sorted(f["path"] for f in version["files"]) == ["RC.pdf", "lot2.zip/RC.pdf"]
    assert any("doublon" in s["reason"] for s in version["skipped"])
