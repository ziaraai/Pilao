import uuid
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import llm
from app.db.models import ComplianceDocument, File, Job, Organization
from app.domain.vault import add_months, paris_today
from app.schemas.vault import ReadingOut
from app.services import vault as svc
from app.services.document_reading import ReadingResult
from tests.api.helpers import register_payload, signed_in_client
from tests.conftest import FakeQueue, FakeReader, MemoryStorage, Outbox
from tests.documents_helpers import make_pdf

Factory = Callable[[], TestClient]
PDF = make_pdf([["Attestation de vigilance", "URSSAF"]])
TODAY = paris_today()
SIREN = register_payload(1)["siret"][:9]


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def reading(**kw: Any) -> ReadingResult:
    data = ReadingOut(
        **{
            "kind": "urssaf_vigilance",
            "issuer": "URSSAF Île-de-France",
            "siren_on_document": SIREN,
            "issued_at": TODAY - timedelta(days=10),
            **kw,
        }
    )
    return ReadingResult(data, data.model_dump(mode="json"), "test/vision", "0.2.0")


def deposit(c: TestClient, content: bytes = PDF, name: str = "attestation.pdf", **form: str) -> Any:
    return c.post("/vault", data=form, files={"file": (name, content, "application/pdf")})


def read_doc(c: TestClient, queue: FakeQueue, reader: FakeReader, **kw: Any) -> str:
    reader.result = reading(**kw)
    res = deposit(c)
    assert res.status_code == 201, res.text
    queue.drain_reads(reader)
    return str(res.json()["id"])


def confirm(c: TestClient, doc_id: str, **kw: Any) -> Any:
    body = {"kind": "urssaf_vigilance", "siren_on_document": SIREN, "valid_until": day(90), **kw}
    return c.put(f"/vault/{doc_id}/confirm", json=body)


def test_upload_read_prefill_then_user_confirms(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    reader.result = reading()
    res = deposit(c)
    body = res.json()
    assert (
        res.status_code == 201
        and body["status"] == "pending_review"
        and body["reading_status"] == "pending"
    )
    assert queue.pending_reads and db.scalars(select(Job)).one().kind == "read_compliance_document"

    queue.drain_reads(reader)
    doc = c.get(f"/vault/{body['id']}").json()
    # AI pre-filled: the 6-month URSSAF rule was applied since no end date was written
    assert doc["reading_status"] == "done" and doc["kind"] == "urssaf_vigilance"
    assert doc["valid_until"] == add_months(TODAY - timedelta(days=10), 6).isoformat()
    assert doc["validity_rule"] == "urssaf_6_months"
    assert doc["status"] == "pending_review"  # NOT usable until the human confirms (CA2)
    stored = db.scalars(select(ComplianceDocument)).one()
    assert stored.extracted["_meta"] == {"model": "test/vision", "prompt_version": "0.2.0"}

    confirmed = confirm(c, body["id"], valid_until=day(120), issuer="URSSAF")
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "valid"
    assert confirmed.json()["days_left"] == 120 and confirmed.json()["confirmed_at"]


def test_confirm_validation(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader
) -> None:
    c = signed_in_client(make_client, outbox)
    doc_id = read_doc(c, queue, reader)
    for patch in (
        {"valid_until": None},  # required for an attestation
        {"valid_until": day(-5), "issued_at": day(0)},  # ends before it starts
        {"siren_on_document": "12345"},
        {"kind": "passport"},
    ):
        assert confirm(c, doc_id, **patch).status_code == 422, patch
    assert (
        confirm(c, doc_id, kind="other", valid_until=None).status_code == 200
    )  # optional for "other"
    assert (
        confirm(
            c, doc_id, siren_on_document="123 456 789".replace("123 456 789", SIREN)
        ).status_code
        == 200
    )


def test_siren_mismatch_alert_and_fix(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader
) -> None:
    c = signed_in_client(make_client, outbox)
    doc_id = read_doc(c, queue, reader, siren_on_document="987654321")
    bad = confirm(c, doc_id, siren_on_document="987654321").json()
    assert bad["status"] == "mismatch"
    assert "987654321" in bad["alerts"][0] and SIREN in bad["alerts"][0]
    assert (
        confirm(c, doc_id, siren_on_document=SIREN).json()["status"] == "valid"
    )  # user corrects it


def test_status_follows_the_calendar(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader
) -> None:
    c = signed_in_client(make_client, outbox)
    ids = {off: read_doc(c, queue, reader) for off in (200, 20, -3)}
    for off, doc_id in ids.items():
        confirm(c, doc_id, valid_until=day(off))
    by_days = {d["days_left"]: d for d in c.get("/vault").json()}
    assert by_days[200]["status"] == "valid" and by_days[20]["status"] == "expiring"
    assert by_days[-3]["status"] == "expired" and "pas inclus" in by_days[-3]["alerts"][0]
    assert {d["id"] for d in c.get("/vault?status=expiring").json()} == {ids[20]}
    assert c.get("/vault?status=bogus").status_code == 422


def test_summary_attention_and_missing(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader
) -> None:
    c = signed_in_client(make_client, outbox)
    empty = c.get("/vault/summary").json()
    assert empty["counts"]["valid"] == 0 and len(empty["missing"]) == 4
    urssaf = read_doc(c, queue, reader)
    confirm(c, urssaf, valid_until=day(300))
    soon = read_doc(c, queue, reader, kind="kbis")
    confirm(c, soon, kind="kbis", valid_until=day(5))
    read_doc(c, queue, reader)  # left unconfirmed
    s = c.get("/vault/summary").json()
    assert s["counts"] == {
        "pending_review": 1,
        "valid": 1,
        "expiring": 1,
        "expired": 0,
        "mismatch": 0,
    }
    assert [a["status"] for a in s["attention"]] == [
        "expiring",
        "pending_review",
    ]  # most urgent first
    missing = [m["label"] for m in s["missing"]]
    assert not any("immatriculation" in m for m in missing)  # an expiring Kbis still counts
    assert not any("URSSAF" in m for m in missing) and len(missing) == 2


def test_reading_unavailable_does_not_block_manual_entry(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader
) -> None:
    c = signed_in_client(make_client, outbox)
    reader.error = llm.LlmNotConfigured("x")
    doc_id = deposit(c).json()["id"]
    queue.drain_reads(reader)
    doc = c.get(f"/vault/{doc_id}").json()
    assert doc["reading_status"] == "error" and "à la main" in doc["reading_error"]
    assert confirm(c, doc_id, kind="tax_compliance").json()["status"] == "valid"


@pytest.mark.parametrize("error", [llm.LlmBudgetExceeded("b"), llm.LlmInvalidOutput("i")])
def test_permanent_ai_errors_are_shown_not_retried(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader, error: Exception
) -> None:
    c = signed_in_client(make_client, outbox)
    reader.error = error
    doc_id = deposit(c).json()["id"]
    queue.drain_reads(reader)  # must not raise
    assert c.get(f"/vault/{doc_id}").json()["reading_status"] == "error"


def test_provider_outage_is_retried_by_the_queue(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader
) -> None:
    c = signed_in_client(make_client, outbox)
    reader.error = llm.LlmProviderError("down")
    doc_id = deposit(c).json()["id"]
    with pytest.raises(llm.LlmProviderError):
        queue.drain_reads(reader)
    assert "nouvelle tentative" in c.get(f"/vault/{doc_id}").json()["reading_error"]
    reader.error, reader.result = None, reading()
    queue.pending_reads.append(uuid.UUID(doc_id))
    queue.drain_reads(reader)
    assert c.get(f"/vault/{doc_id}").json()["reading_status"] == "done"


def test_ai_never_overwrites_what_the_user_already_confirmed(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader
) -> None:
    c = signed_in_client(make_client, outbox)
    reader.result = reading(kind="kbis", valid_until=date(2031, 1, 1))
    doc_id = deposit(c).json()["id"]
    confirm(c, doc_id, kind="tax_compliance", valid_until=day(60))  # the user was faster
    queue.drain_reads(reader)
    doc = c.get(f"/vault/{doc_id}").json()
    assert doc["kind"] == "tax_compliance" and doc["valid_until"] == day(60)
    assert doc["reading_status"] == "done"


def test_reread_rules(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader
) -> None:
    c = signed_in_client(make_client, outbox)
    reader.error = llm.LlmInvalidOutput("x")
    doc_id = deposit(c).json()["id"]
    assert c.post(f"/vault/{doc_id}/reread").status_code == 409  # still queued
    queue.drain_reads(reader)
    reader.error, reader.result = None, reading()
    assert c.post(f"/vault/{doc_id}/reread").status_code == 202
    queue.drain_reads(reader)
    confirm(c, doc_id)
    assert c.post(f"/vault/{doc_id}/reread").json()["error"]["code"] == "already_confirmed"


def test_queue_down_is_visible(make_client: Factory, outbox: Outbox, queue: FakeQueue) -> None:
    c = signed_in_client(make_client, outbox)
    queue.down = True
    res = deposit(c)
    assert res.status_code == 201 and res.json()["reading_status"] == "error"


def test_delete_removes_file_and_object(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    reader: FakeReader,
    storage: MemoryStorage,
    db: Session,
) -> None:
    c = signed_in_client(make_client, outbox)
    doc_id = read_doc(c, queue, reader)
    assert c.delete(f"/vault/{doc_id}").status_code == 204
    assert (
        db.scalars(select(ComplianceDocument)).all() == [] and db.scalars(select(File)).all() == []
    )
    assert storage.objects == {} and c.get(f"/vault/{doc_id}").status_code == 404


def test_upload_type_and_virus_checks(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, storage: MemoryStorage
) -> None:
    c = signed_in_client(make_client, outbox)
    from tests.documents_helpers import make_docx

    assert deposit(c, make_docx([("Normal", "x")]), "a.docx").status_code == 415
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 30
    assert deposit(c, png, "scan.png").status_code == 201  # images are fine (scans)
    assert (
        deposit(c, b"%PDF-1.4 EICAR-STANDARD-ANTIVIRUS-TEST-FILE").json()["error"]["code"]
        == "infected_file"
    )
    assert deposit(c, PDF, kind="passport").status_code == 422
    assert len(storage.objects) == 1


def test_help_links(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    links = {x["kind"]: x for x in c.get("/vault/help-links").json()}
    assert {"kbis", "rne_certificate", "urssaf_vigilance", "tax_compliance"} <= set(links)
    assert all(x["url"].startswith("https://") for x in links.values())


def test_expired_or_unconfirmed_documents_are_excluded_from_exports(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    ok, expired, mismatch = (read_doc(c, queue, reader) for _ in range(3))
    read_doc(c, queue, reader)  # unconfirmed
    confirm(c, ok, valid_until=day(100))
    confirm(c, expired, valid_until=day(-1))
    confirm(c, mismatch, siren_on_document="987654321")
    org = db.scalars(select(Organization)).one()
    usable = svc.usable_documents(db, org, TODAY)
    assert [str(d.id) for d in usable] == [ok]


def test_stored_status_is_refreshed_by_the_daily_job(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, reader: FakeReader, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    doc_id = read_doc(c, queue, reader)
    confirm(c, doc_id, valid_until=day(1))
    assert svc.refresh_stored_statuses(db, TODAY + timedelta(days=5)) == 1
    db.expire_all()
    assert db.scalars(select(ComplianceDocument)).one().status == "expired"
    assert svc.refresh_stored_statuses(db, TODAY + timedelta(days=5)) == 0  # idempotent


def test_requires_authentication(make_client: Factory) -> None:
    anon = make_client()
    assert anon.get("/vault").status_code == 401
    assert anon.get("/vault/summary").status_code == 401
    assert anon.get("/vault/help-links").status_code == 401
    assert deposit(anon).status_code == 401


def test_tenancy_isolation(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    reader: FakeReader,
    storage: MemoryStorage,
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    doc_id = read_doc(b, queue, reader)
    confirm(b, doc_id, siren_on_document=register_payload(2)["siret"][:9])
    assert a.get("/vault").json() == [] and a.get("/vault/summary").json()["counts"]["valid"] == 0
    assert a.get(f"/vault/{doc_id}").status_code == 404
    assert confirm(a, doc_id).status_code == 404
    assert a.post(f"/vault/{doc_id}/reread").status_code == 404
    assert a.delete(f"/vault/{doc_id}").status_code == 404
    assert b.get(f"/vault/{doc_id}").json()["status"] == "valid" and storage.objects
