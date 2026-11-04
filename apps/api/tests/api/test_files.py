import io
import zipfile
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AuditLog, File
from tests.api.helpers import signed_in_client
from tests.conftest import FakeScanner, MemoryStorage, Outbox

Factory = Callable[[], TestClient]
PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\n%%EOF"
EICAR = b"%PDF-1.4\nX5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def make_zip(names: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for n, content in names.items():
            zf.writestr(n, content)
    return out.getvalue()


def up(c: TestClient, content: bytes, name: str = "doc.pdf", ctype: str = "application/pdf"):  # type: ignore[no-untyped-def]
    return c.post("/files", files={"file": (name, content, ctype)})


def test_upload_pdf_stores_object_and_metadata(
    make_client: Factory, outbox: Outbox, storage: MemoryStorage, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    res = up(c, PDF, "Mémoire technique.pdf")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["mime"] == "application/pdf" and body["size_bytes"] == len(PDF)
    assert body["filename"] == "Mémoire technique.pdf" and len(body["sha256"]) == 64
    record = db.scalars(select(File)).one()
    assert storage.objects[record.storage_key] == PDF
    assert record.storage_key.startswith(f"{record.org_id}/")  # per-org prefix, no user filename
    assert "Mémoire" not in record.storage_key
    assert db.scalars(select(AuditLog).where(AuditLog.action == "upload")).one()


def test_type_is_detected_from_content_not_from_client(
    make_client: Factory, outbox: Outbox
) -> None:
    c = signed_in_client(make_client, outbox)
    docx = make_zip({"word/document.xml": b"<w/>", "[Content_Types].xml": b""})
    xlsx = make_zip({"xl/workbook.xml": b"<w/>"})
    plain_zip = make_zip({"a.txt": b"hello"})
    assert (
        up(c, docx, "x.bin", "application/octet-stream")
        .json()["mime"]
        .endswith("wordprocessingml.document")
    )
    assert up(c, docx, "x.bin").json()["filename"] == "x.bin.docx"
    assert up(c, xlsx, "t.xlsx").json()["mime"].endswith("spreadsheetml.sheet")
    assert up(c, plain_zip, "dce.zip").json()["mime"] == "application/zip"
    assert up(c, b"\x89PNG\r\n\x1a\n" + b"0" * 20, "p.png").json()["mime"] == "image/png"
    assert up(c, b"\xff\xd8\xff\xe0" + b"0" * 20, "p.jpg").json()["mime"] == "image/jpeg"


def test_rejects_unsupported_and_disguised_files(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    for content, name in [
        (b"MZ\x90\x00 an executable", "memo.pdf"),  # exe renamed .pdf
        (b"<html><script>alert(1)</script></html>", "page.html"),
        (b"just text", "notes.txt"),
        (b"PK\x03\x04 broken zip", "broken.zip"),
    ]:
        res = up(c, content, name)
        assert res.status_code == 415 and res.json()["error"]["code"] == "unsupported_type", name
    assert up(c, b"", "empty.pdf").json()["error"]["code"] == "empty_file"


def test_filename_is_sanitized(make_client: Factory, outbox: Outbox) -> None:
    from app.services.files import clean_filename

    assert clean_filename("../../etc/passwd", "pdf") == "passwd.pdf"
    assert clean_filename("C:\\Users\\x\\doc.pdf", "pdf") == "doc.pdf"
    assert clean_filename("a\x00b\nc.pdf", "pdf") == "a_b_c.pdf"
    assert clean_filename("   ...  ", "pdf") == "document.pdf"
    assert clean_filename(None, "zip") == "document.zip"
    assert clean_filename("rapport", "docx") == "rapport.docx"
    assert len(clean_filename("x" * 500 + ".pdf", "pdf")) <= 210
    c = signed_in_client(make_client, outbox)
    assert up(c, PDF, "../../etc/passwd").json()["filename"] == "passwd.pdf"


def test_size_limit(make_client: Factory, outbox: Outbox, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c = signed_in_client(make_client, outbox)
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1000)
    res = up(c, PDF + b"0" * 2000)
    assert res.status_code == 413 and res.json()["error"]["code"] == "file_too_large"


def test_oversized_content_length_is_refused_before_reading(
    make_client: Factory, outbox: Outbox, monkeypatch  # type: ignore[no-untyped-def]
) -> None:
    c = signed_in_client(make_client, outbox)
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 100)
    big = PDF + b"0" * (3 * 1024 * 1024)
    res = up(c, big)  # refused by the middleware itself, not by the service after spooling
    assert res.status_code == 413 and res.json()["error"]["code"] == "payload_too_large"


def test_chunked_body_without_content_length_is_bounded_too(
    make_client: Factory, outbox: Outbox, monkeypatch  # type: ignore[no-untyped-def]
) -> None:
    c = signed_in_client(make_client, outbox)
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 100)

    def chunks():  # type: ignore[no-untyped-def]
        for _ in range(3):
            yield b"0" * (1024 * 1024)

    res = c.post(
        "/files", content=chunks(), headers={"Content-Type": "multipart/form-data; boundary=x"}
    )
    assert res.status_code == 413 and res.json()["error"]["code"] == "payload_too_large"


def test_jpeg_spellings_and_invisible_characters_in_names() -> None:
    from app.services.files import clean_filename

    assert clean_filename("photo.jpeg", "jpg") == "photo.jpeg"
    assert clean_filename("photo.JPG", "jpg") == "photo.JPG"
    assert clean_filename("facture\u202efdp.exe", "pdf") == "facturefdp.exe.pdf"
    assert clean_filename("a\x85b.pdf", "pdf") == "a_b.pdf"


def test_file_used_as_reference_photo_cannot_be_deleted(
    make_client: Factory, outbox: Outbox, storage: MemoryStorage
) -> None:
    c = signed_in_client(make_client, outbox)
    fid = up(c, b"\x89PNG\r\n\x1a\n" + b"0" * 20, "p.png").json()["id"]
    ref = {"client_name": "A", "client_type": "public", "title": "T", "photo_file_ids": [fid]}
    assert c.post("/profile/references", json=ref).status_code == 201
    res = c.delete(f"/files/{fid}")
    assert res.status_code == 409 and res.json()["error"]["code"] == "file_in_use"
    assert len(storage.objects) == 1


def test_production_without_antivirus_refuses_to_start(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import pytest

    from app.main import app
    from app.storage.antivirus import ScannerUnavailable, get_scanner

    get_scanner.cache_clear()
    monkeypatch.setattr(get_settings(), "environment", "production")
    monkeypatch.setattr(get_settings(), "clamav_host", None)
    try:
        with pytest.raises(ScannerUnavailable), TestClient(app):
            pass
    finally:
        get_scanner.cache_clear()


def test_org_storage_quota(make_client: Factory, outbox: Outbox, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    c = signed_in_client(make_client, outbox)
    monkeypatch.setattr(get_settings(), "org_storage_quota_bytes", len(PDF) * 2)
    assert up(c, PDF).status_code == 201 and up(c, PDF).status_code == 201
    res = up(c, PDF)
    assert res.status_code == 413 and res.json()["error"]["code"] == "quota_exceeded"


def test_infected_file_is_refused_not_stored_and_audited(
    make_client: Factory, outbox: Outbox, storage: MemoryStorage, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    res = up(c, EICAR)
    assert res.status_code == 422 and res.json()["error"]["code"] == "infected_file"
    assert storage.objects == {} and db.scalars(select(File)).all() == []
    log = db.scalars(select(AuditLog).where(AuditLog.action == "upload_blocked")).one()
    assert log.meta["signature"] == "Eicar-Test-Signature"


def test_scanner_outage_fails_closed(
    make_client: Factory, outbox: Outbox, scanner: FakeScanner, storage: MemoryStorage
) -> None:
    c = signed_in_client(make_client, outbox)
    scanner.down = True
    res = up(c, PDF)
    assert res.status_code == 503 and storage.objects == {}


def test_database_failure_removes_orphan_object(
    make_client: Factory, outbox: Outbox, storage: MemoryStorage, monkeypatch  # type: ignore[no-untyped-def]
) -> None:
    c = signed_in_client(make_client, outbox)
    from sqlalchemy.orm import Session as S

    original = S.commit

    def boom(self):  # type: ignore[no-untyped-def]
        if any(isinstance(o, File) for o in self.new):
            raise RuntimeError("db down")
        return original(self)

    monkeypatch.setattr(S, "commit", boom)
    c2 = TestClient(
        c.app, raise_server_exceptions=False, headers=dict(c.headers), cookies=c.cookies
    )
    assert up(c2, PDF).status_code == 500
    assert storage.objects == {}


def test_failed_cleanup_does_not_hide_the_database_error(
    make_client: Factory, outbox: Outbox, storage: MemoryStorage, monkeypatch  # type: ignore[no-untyped-def]
) -> None:
    import pytest
    from sqlalchemy.orm import Session as S

    c = signed_in_client(make_client, outbox)
    original = S.commit

    def boom(self):  # type: ignore[no-untyped-def]
        if any(isinstance(o, File) for o in self.new):
            raise RuntimeError("db down")
        return original(self)

    def broken_delete(key: str) -> None:
        raise ConnectionError("s3 down")

    monkeypatch.setattr(S, "commit", boom)
    monkeypatch.setattr(storage, "delete", broken_delete)
    with pytest.raises(RuntimeError, match="db down"):
        up(c, PDF)


def test_storage_failure_creates_no_database_row(
    make_client: Factory, outbox: Outbox, storage: MemoryStorage, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    storage.fail_put = True
    c2 = TestClient(
        c.app, raise_server_exceptions=False, headers=dict(c.headers), cookies=c.cookies
    )
    assert up(c2, PDF).status_code == 500
    assert db.scalars(select(File)).all() == []


def test_list_get_download_and_delete(
    make_client: Factory, outbox: Outbox, storage: MemoryStorage
) -> None:
    c = signed_in_client(make_client, outbox)
    ids = [up(c, PDF, f"f{i}.pdf").json()["id"] for i in range(3)]
    assert len(c.get("/files").json()) == 3 and len(c.get("/files?limit=2").json()) == 2
    assert c.get(f"/files/{ids[0]}").json()["filename"] == "f0.pdf"
    dl = c.get(f"/files/{ids[0]}/download-url").json()
    assert dl["expires_in"] == 300 and "expires=300" in dl["url"] and "f0.pdf" in dl["url"]
    assert c.delete(f"/files/{ids[0]}").status_code == 204
    assert c.get(f"/files/{ids[0]}").status_code == 404 and len(storage.objects) == 2


def test_requires_authentication(make_client: Factory) -> None:
    anon = make_client()
    assert anon.get("/files").status_code == 401
    assert up(anon, PDF).status_code == 401
    assert anon.get("/files/00000000-0000-0000-0000-000000000000/download-url").status_code == 401


def test_tenancy_isolation(make_client: Factory, outbox: Outbox, storage: MemoryStorage) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    fid = up(b, PDF).json()["id"]
    assert a.get("/files").json() == []
    assert a.get(f"/files/{fid}").status_code == 404
    assert a.get(f"/files/{fid}/download-url").status_code == 404
    assert a.delete(f"/files/{fid}").status_code == 404
    assert len(storage.objects) == 1 and b.get(f"/files/{fid}").status_code == 200
