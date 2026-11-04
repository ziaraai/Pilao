import io
import uuid
import zipfile
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DceFile, File
from tests.api.helpers import signed_in_client
from tests.conftest import FakeQueue, FakeScanner, MemoryStorage, Outbox
from tests.documents_helpers import make_docx, make_pdf

Factory = Callable[[], TestClient]
RC = make_pdf([["REGLEMENT DE LA CONSULTATION", "Date limite : 15 decembre"]])
CCTP_V1 = make_pdf([["CAHIER DES CLAUSES TECHNIQUES", "Nettoyage quotidien des bureaux"]])
CCTP_V2 = make_pdf([["CAHIER DES CLAUSES TECHNIQUES", "Nettoyage biquotidien des bureaux"]])
EICAR = b"%PDF-1.4 X5O!P%@AP EICAR-STANDARD-ANTIVIRUS-TEST-FILE"


def zipped(entries: dict[str, bytes], method: int = zipfile.ZIP_DEFLATED) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", method) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return out.getvalue()


def new_bid(c: TestClient, **kw: Any) -> str:
    res = c.post(
        "/bids", json={"title": "Nettoyage des écoles", "buyer_name": "Ville de Lyon", **kw}
    )
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


def deposit(c: TestClient, bid_id: str, *files: tuple[str, bytes]) -> Any:
    return c.post(
        f"/bids/{bid_id}/dce",
        files=[("files", (name, content, "application/octet-stream")) for name, content in files],
    )


def processed(
    c: TestClient, queue: FakeQueue, bid_id: str, *files: tuple[str, bytes]
) -> dict[str, Any]:
    res = deposit(c, bid_id, *files)
    assert res.status_code == 202, res.text
    queue.drain_dce()
    return c.get(f"/bids/{bid_id}/dce/{res.json()['version']}").json()  # type: ignore[no-any-return]


# ---------- bids --------------------------------------------------------------------------


def test_bid_crud(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    late = new_bid(c, deadline_at="2027-03-01T12:00:00+01:00")
    soon = new_bid(c, title="Vitrerie mairie", deadline_at="2026-12-15T12:00:00+01:00")
    undated = new_bid(c, title="Sans date")
    assert [b["id"] for b in c.get("/bids").json()] == [
        soon,
        late,
        undated,
    ]  # nearest deadline first
    body = c.get(f"/bids/{soon}").json()
    assert body["status"] == "to_review" and body["buyer_name"] == "Ville de Lyon"

    patched = c.patch(
        f"/bids/{soon}", json={"status": "won", "result_rank": 1, "submitted_amount_cents": 4500000}
    )
    assert (
        patched.json()["status"] == "won" and patched.json()["title"] == "Vitrerie mairie"
    )  # untouched
    assert [b["id"] for b in c.get("/bids?status=won").json()] == [soon]
    assert c.patch(f"/bids/{soon}", json={"title": None}).json()["title"] == "Vitrerie mairie"
    assert c.patch(f"/bids/{soon}", json={"status": "gagné"}).status_code == 422
    assert c.patch(f"/bids/{soon}", json={"result_rank": 0}).status_code == 422
    assert c.post("/bids", json={"title": "  "}).status_code == 422
    assert (
        c.delete(f"/bids/{soon}").status_code == 204 and c.get(f"/bids/{soon}").status_code == 404
    )


# ---------- DCE deposit -------------------------------------------------------------------


def test_zip_is_expanded_typed_and_reported(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    annexes = zipped(
        {"Annexe 1 au CCTP - liste des locaux.pdf": RC, "plans/plan_RDC.dwg": b"AC1027"}
    )
    dce = zipped(
        {
            "DCE/RC_2026-045.pdf": RC,
            "DCE/CCTP.pdf": CCTP_V1,
            "DCE/Acte d'engagement.docx": make_docx([("Normal", "Acte d'engagement")]),
            "DCE/annexes.zip": annexes,
            "__MACOSX/DCE/._RC.pdf": b"x",
        }
    )
    res = deposit(c, bid, ("DCE consultation.zip", dce))
    assert (
        res.status_code == 202 and res.json()["status"] == "pending" and res.json()["version"] == 1
    )
    queue.drain_dce()
    version = c.get(f"/bids/{bid}/dce/1").json()
    assert version["status"] == "ready" and version["error"] is None
    kinds = {f["path"]: f["detected_kind"] for f in version["files"]}
    assert kinds == {
        "DCE/RC_2026-045.pdf": "rc",
        "DCE/CCTP.pdf": "cctp",
        "DCE/Acte d'engagement.docx": "ae",
        "DCE/annexes.zip/Annexe 1 au CCTP - liste des locaux.pdf": "annex",
    }
    assert all(f["kind_source"] == "filename" and not f["kind_confirmed"] for f in version["files"])
    assert version["skipped"] == [
        {"path": "DCE/annexes.zip/plans/plan_RDC.dwg", "reason": "format non pris en charge"}
    ]
    assert version["diff"] is None  # first version


def test_several_documents_can_be_deposited_without_zip(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    version = processed(c, queue, bid, ("RC.pdf", RC), ("CCTP.pdf", CCTP_V1))
    assert sorted(f["path"] for f in version["files"]) == ["CCTP.pdf", "RC.pdf"]


def test_new_deposit_is_a_new_version_with_differences(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    processed(
        c,
        queue,
        bid,
        ("DCE.zip", zipped({"RC.pdf": RC, "CCTP.pdf": CCTP_V1, "Annexe.pdf": RC + b"%"})),
    )
    v2 = processed(
        c,
        queue,
        bid,
        (
            "DCE_modifie_v2.zip",
            zipped(
                {
                    "RC.pdf": RC,
                    "CCTP.pdf": CCTP_V2,
                    "BPU.xlsx": _xlsx(),
                }
            ),
        ),
    )
    assert v2["version"] == 2
    assert v2["diff"] == {
        "previous_version": 1,
        "added": ["BPU.xlsx"],
        "removed": ["Annexe.pdf"],
        "modified": ["CCTP.pdf"],
    }
    assert v2["diff_summary"] == (
        "Par rapport à la version 1 : 1 fichier modifié (CCTP.pdf), 1 ajouté (BPU.xlsx), "
        "1 supprimé (Annexe.pdf)."
    )
    same = processed(
        c,
        queue,
        bid,
        ("encore.zip", zipped({"RC.pdf": RC, "CCTP.pdf": CCTP_V2, "BPU.xlsx": _xlsx()})),
    )
    assert same["diff_summary"] == "Aucun changement de fichier par rapport à la version 2."
    assert [v["version"] for v in c.get(f"/bids/{bid}/dce").json()] == [3, 2, 1]


def _xlsx() -> bytes:
    from openpyxl import Workbook

    out = io.BytesIO()
    Workbook().save(out)
    return out.getvalue()


def test_infected_member_is_skipped_others_kept(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    version = processed(c, queue, bid, ("DCE.zip", zipped({"RC.pdf": RC, "CCTP.pdf": EICAR})))
    assert [f["path"] for f in version["files"]] == ["RC.pdf"]
    assert (
        version["skipped"][0]["path"] == "CCTP.pdf" and "virus" in version["skipped"][0]["reason"]
    )


def test_zip_bomb_fails_the_version_and_keeps_nothing(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, storage: MemoryStorage, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    bomb = zipped({"RC.pdf": RC, "bombe.pdf": b"%PDF" + b"\0" * (40 * 1024 * 1024)})
    version = processed(c, queue, bid, ("DCE.zip", bomb))
    assert version["status"] == "error" and "compression anormal" in version["error"]
    assert version["files"] == [] and db.scalars(select(DceFile)).all() == []
    assert len(storage.objects) == 1  # only the deposited archive itself


def test_nothing_usable_is_an_error(make_client: Factory, outbox: Outbox, queue: FakeQueue) -> None:
    c = signed_in_client(make_client, outbox)
    version = processed(c, queue, new_bid(c), ("plans.zip", zipped({"plan.dwg": b"AC1027"})))
    assert version["status"] == "error" and "Aucun fichier exploitable" in version["error"]


def test_deposit_validation(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, storage: MemoryStorage
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    assert deposit(c, bid, ("notes.txt", b"bonjour")).status_code == 415
    assert c.post(f"/bids/{bid}/dce").status_code == 422  # no file at all
    # A failing file in the batch: nothing from the batch is kept.
    assert deposit(c, bid, ("RC.pdf", RC), ("x.txt", b"bonjour")).status_code == 415
    assert storage.objects == {} and c.get(f"/bids/{bid}/dce").json() == []


def test_only_one_deposit_processed_at_a_time(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    assert deposit(c, bid, ("RC.pdf", RC)).status_code == 202
    res = deposit(c, bid, ("RC.pdf", RC))
    assert res.status_code == 409 and res.json()["error"]["code"] == "dce_processing"
    queue.drain_dce()
    assert deposit(c, bid, ("RC.pdf", RC)).status_code == 202


def test_transient_failure_is_retried_without_duplicates(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, scanner: FakeScanner, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    res = deposit(c, bid, ("DCE.zip", zipped({"RC.pdf": RC, "CCTP.pdf": CCTP_V1})))
    scanner.down = True
    with pytest.raises(Exception):  # noqa: B017 - the worker re-raises so that RQ retries
        queue.drain_dce()
    assert "nouvelle tentative" in c.get(f"/bids/{bid}/dce/1").json()["error"]
    scanner.down = False
    queue.pending_dce.append(uuid.UUID(res.json()["id"]))
    queue.drain_dce()
    version = c.get(f"/bids/{bid}/dce/1").json()
    assert version["status"] == "ready" and len(version["files"]) == 2
    assert len(db.scalars(select(DceFile)).all()) == 2


def test_queue_down_is_visible(make_client: Factory, outbox: Outbox, queue: FakeQueue) -> None:
    c = signed_in_client(make_client, outbox)
    queue.down = True
    res = deposit(c, new_bid(c), ("RC.pdf", RC))
    assert res.status_code == 202 and res.json()["status"] == "error"


def test_user_corrects_the_kind(make_client: Factory, outbox: Outbox, queue: FakeQueue) -> None:
    c = signed_in_client(make_client, outbox)
    letter = make_pdf([["Lettre d'information aux candidats", "Merci de votre interet"]])
    version = processed(c, queue, new_bid(c), ("piece3.pdf", letter))
    file_id = version["files"][0]["id"]
    assert version["files"][0]["detected_kind"] == "other"  # neither name nor title helps
    fixed = c.patch(f"/dce-files/{file_id}", json={"kind": "rc"}).json()
    assert (
        fixed["detected_kind"] == "rc"
        and fixed["kind_confirmed"]
        and fixed["kind_source"] == "user"
    )
    assert c.patch(f"/dce-files/{file_id}", json={"kind": "devis"}).status_code == 422


def test_deleting_a_bid_removes_every_file(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, storage: MemoryStorage, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    processed(c, queue, bid, ("DCE.zip", zipped({"RC.pdf": RC, "CCTP.pdf": CCTP_V1})))
    processed(c, queue, bid, ("CCTP.pdf", CCTP_V2))
    assert len(storage.objects) == 5
    assert c.delete(f"/bids/{bid}").status_code == 204
    assert storage.objects == {} and db.scalars(select(File)).all() == []


def test_dce_files_cannot_be_deleted_from_files_endpoint(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c)
    version = processed(c, queue, bid, ("DCE.zip", zipped({"RC.pdf": RC})))
    member = version["files"][0]["file_id"]
    source = next(f["id"] for f in c.get("/files").json() if f["filename"] == "DCE.zip")
    for file_id in (member, source):
        assert c.delete(f"/files/{file_id}").json()["error"]["code"] == "file_in_use"


def test_requires_authentication(make_client: Factory) -> None:
    anon = make_client()
    assert anon.get("/bids").status_code == 401
    assert anon.post("/bids", json={"title": "x"}).status_code == 401
    assert anon.patch(f"/dce-files/{uuid.uuid4()}", json={"kind": "rc"}).status_code == 401


def test_tenancy_isolation(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, storage: MemoryStorage
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    bid = new_bid(b)
    version = processed(b, queue, bid, ("RC.pdf", RC))
    file_id = version["files"][0]["id"]
    assert a.get("/bids").json() == []
    assert a.get(f"/bids/{bid}").status_code == 404
    assert a.patch(f"/bids/{bid}", json={"status": "dropped"}).status_code == 404
    assert a.delete(f"/bids/{bid}").status_code == 404
    assert deposit(a, bid, ("RC.pdf", RC)).status_code == 404
    assert a.get(f"/bids/{bid}/dce").status_code == 404
    assert a.patch(f"/dce-files/{file_id}", json={"kind": "rc"}).status_code == 404
    assert b.get(f"/bids/{bid}").json()["status"] == "to_review"
    assert b.get(f"/bids/{bid}/dce/1").json()["files"][0]["detected_kind"] == "rc"


def test_dce_endpoint_gets_the_larger_body_limit() -> None:
    from app.core.limits import _DCE_UPLOAD

    assert _DCE_UPLOAD.match(f"/bids/{uuid.uuid4()}/dce")
    assert not _DCE_UPLOAD.match("/files") and not _DCE_UPLOAD.match("/bids/x/dce/1")


def test_same_content_under_two_names_is_kept(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    version = processed(
        c, queue, new_bid(c), ("DCE.zip", zipped({"RC.pdf": RC, "Annexe RC copie.pdf": RC}))
    )
    assert sorted(f["path"] for f in version["files"]) == ["Annexe RC copie.pdf", "RC.pdf"]


# ---------- page-by-page text, OCR, typing by content (delivery 2) ------------------------

from tests.documents_helpers import make_scanned_pdf


class FakeOcr:
    def image_to_text(self, image: Any) -> str:
        return "REGLEMENT DE LA CONSULTATION\nDate limite de remise des offres : 15 décembre"


def test_pages_are_extracted_and_served(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    cctp = make_pdf(
        [[f"Article {i} - Nettoyage des locaux, prestation numero {i}"] for i in range(1, 4)][0:1]
        * 3
    )
    version = processed(c, queue, new_bid(c), ("CCTP.pdf", cctp))
    f = version["files"][0]
    assert (f["text_status"], f["page_count"], f["paginated"], f["ocr_used"]) == (
        "ready",
        3,
        True,
        False,
    )
    pages = c.get(f"/dce-files/{f['id']}/pages").json()
    assert [p["page"] for p in pages] == [1, 2, 3] and "Nettoyage des locaux" in pages[0]["text"]
    assert [
        p["page"]
        for p in c.get(f"/dce-files/{f['id']}/pages", params={"from": 2, "count": 1}).json()
    ] == [2]
    assert c.get(f"/dce-files/{f['id']}/pages", params={"count": 500}).status_code == 422


def test_unnamed_piece_is_typed_from_its_first_page(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    titled = make_pdf(
        [
            [
                "CAHIER DES CLAUSES TECHNIQUES PARTICULIERES",
                "Voir aussi le reglement de la consultation",
            ]
        ]
    )
    version = processed(c, queue, new_bid(c), ("piece_02.pdf", titled))
    f = version["files"][0]
    assert f["detected_kind"] == "cctp" and f["kind_source"] == "content"


def test_scanned_piece_without_ocr_is_flagged_but_version_ready(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    version = processed(c, queue, new_bid(c), ("scan.pdf", make_scanned_pdf(["x"])))
    assert version["status"] == "ready"
    assert version["files"][0]["text_status"] == "ocr_unavailable"


def test_scanned_piece_goes_through_ocr_and_is_typed(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    queue.ocr = FakeOcr()
    version = processed(c, queue, new_bid(c), ("scan_001.pdf", make_scanned_pdf(["x"], pages=2)))
    f = version["files"][0]
    assert f["ocr_used"] and f["text_status"] == "ready" and f["detected_kind"] == "rc"
    pages = c.get(f"/dce-files/{f['id']}/pages").json()
    assert all(p["ocr_used"] and "15 décembre" in p["text"] for p in pages)


def test_word_piece_is_unpaginated(make_client: Factory, outbox: Outbox, queue: FakeQueue) -> None:
    c = signed_in_client(make_client, outbox)
    version = processed(
        c,
        queue,
        new_bid(c),
        ("CCAP.docx", make_docx([("Normal", "Pénalités de retard : 100 € par jour.")])),
    )
    f = version["files"][0]
    assert (f["paginated"], f["page_count"], f["detected_kind"]) == (False, None, "ccap")
    assert "Pénalités" in c.get(f"/dce-files/{f['id']}/pages").json()[0]["text"]


def test_pages_are_tenant_isolated(make_client: Factory, outbox: Outbox, queue: FakeQueue) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    version = processed(b, queue, new_bid(b), ("RC.pdf", RC))
    file_id = version["files"][0]["id"]
    assert a.get(f"/dce-files/{file_id}/pages").status_code == 404
    assert b.get(f"/dce-files/{file_id}/pages").status_code == 200


def test_rq_enqueue_targets_the_dce_job() -> None:
    import fakeredis
    from rq import Queue

    from app.workers.queue import DCE_JOB_TIMEOUT_SECONDS, RqJobQueue

    q = Queue("default", connection=fakeredis.FakeRedis())
    version_id = uuid.uuid4()
    RqJobQueue(q).enqueue_process_dce(version_id)
    (job,) = q.jobs
    assert job.func_name == "app.workers.jobs.process_dce_job" and job.args == (str(version_id),)
    assert job.timeout == DCE_JOB_TIMEOUT_SECONDS and job.retries_left == 2
