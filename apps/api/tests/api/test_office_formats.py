"""LibreOffice and Office 97-2003 files (ADR-034): recognized from their content, read
after a LibreOffice conversion, and kept as deposited. Abdraouf's memoir is an .odt."""

import io
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.core.config import get_settings
from app.documents.pages import extract_pages
from app.domain.filetypes import DOC, ODS, ODT, XLS, ZIP, detect
from app.services.knowledge import _blocks
from tests.api.helpers import signed_in_client
from tests.api.test_bids import deposit as deposit_dce
from tests.api.test_bids import new_bid, zipped
from tests.api.test_knowledge import deposit as deposit_doc
from tests.conftest import FakeQueue, MemoryStorage, Outbox

pytestmark = pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice absent")
Factory = Callable[[], TestClient]


def _two_pages_docx() -> bytes:
    doc = Document()
    doc.add_heading("Méthodologie", level=1)
    doc.add_paragraph("Article 1 : nettoyage quotidien des bureaux avant 8h.")
    doc.add_page_break()
    doc.add_paragraph("Article 2 : vitrerie intérieure une fois par trimestre.")
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def _sheet() -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["Désignation", "Unité", "Prix unitaire"])
    ws.append(["Nettoyage final avant réception", "FF", 2404])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def office(data: bytes, source: str, target: str) -> bytes:
    """A real file of the target format, written by LibreOffice."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / f"f.{source}").write_bytes(data)
        subprocess.run(
            [
                "soffice",
                "--headless",
                f"-env:UserInstallation={(work / 'p').as_uri()}",
                "--convert-to",
                target,
                "--outdir",
                str(work),
                str(work / f"f.{source}"),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        return (work / f"f.{target}").read_bytes()


@pytest.fixture(scope="module")
def files() -> dict[str, bytes]:
    text, sheet = _two_pages_docx(), _sheet()
    return {
        "odt": office(text, "docx", "odt"),
        "doc": office(text, "docx", "doc"),
        "ods": office(sheet, "xlsx", "ods"),
        "xls": office(sheet, "xlsx", "xls"),
    }


def test_the_formats_are_recognized_from_their_content(files: dict[str, bytes]) -> None:
    for ext, kind in (("odt", ODT), ("doc", DOC), ("ods", ODS), ("xls", XLS)):
        stream = io.BytesIO(files[ext])
        assert detect(stream) == kind and stream.tell() == 0, ext
    # what only looks like them is not taken for them
    assert detect(io.BytesIO(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 600)) is None
    fake = io.BytesIO()
    with zipfile.ZipFile(fake, "w") as zf:
        zf.writestr("mimetype", "application/vnd.oasis.opendocument.text")  # no content.xml
    assert detect(fake) == ZIP


def test_a_dce_piece_keeps_its_pages_and_a_sheet_its_rows(files: dict[str, bytes]) -> None:
    for ext in ("odt", "doc"):
        mime = detect(io.BytesIO(files[ext])).mime  # type: ignore[union-attr]
        result = extract_pages(io.BytesIO(files[ext]), mime, None)
        assert result.status == "ready" and result.paginated, ext  # read as a PDF
        assert [p.page for p in result.pages] == [1, 2]
        assert "nettoyage quotidien" in result.pages[0].text and "vitrerie" in result.pages[1].text
    for ext in ("ods", "xls"):
        mime = detect(io.BytesIO(files[ext])).mime  # type: ignore[union-attr]
        result = extract_pages(io.BytesIO(files[ext]), mime, None)
        assert (
            result.status == "ready" and "Nettoyage final avant réception" in result.pages[0].text
        )


def test_a_knowledge_document_keeps_its_headings(files: dict[str, bytes]) -> None:
    blocks = _blocks(io.BytesIO(files["odt"]), ODT.mime)
    assert ("heading", "Méthodologie") in [(b.kind, b.text) for b in blocks]  # read as a DOCX
    assert any("vitrerie" in b.text for b in _blocks(io.BytesIO(files["doc"]), DOC.mime))


def test_without_libreoffice_the_piece_says_why(
    files: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "soffice_path", "soffice-introuvable")
    result = extract_pages(io.BytesIO(files["odt"]), ODT.mime, None)
    assert result.status == "error"
    assert result.error == "Lecture impossible : LibreOffice n'est pas installé sur le serveur."


def test_deposits_accept_them_and_keep_the_original(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    storage: MemoryStorage,
    files: dict[str, bytes],
) -> None:
    c = signed_in_client(make_client, outbox)
    # the knowledge base: Abdraouf's memoir in .odt, an old .doc
    for name in ("memoire-2017.odt", "procedures.doc"):
        res = deposit_doc(c, files[name.rsplit(".", 1)[1]], name)
        assert res.status_code == 201, res.text
    queue.drain()
    docs = c.get("/knowledge").json()
    assert {d["status"] for d in docs} == {"ready"} and len(docs) == 2
    sheet = deposit_doc(c, files["ods"], "prix.ods")
    assert sheet.status_code == 415  # a spreadsheet is no memoir
    assert sheet.json()["error"]["message"].endswith("(PDF, DOCX, ODT, DOC).")
    assert files["odt"] in storage.objects.values()  # stored as deposited, never replaced

    # a DCE: RC in .odt, BPU in .xls, inside a ZIP
    bid = new_bid(c)
    dce = zipped({"DCE/RC.odt": files["odt"], "DCE/BPU.xls": files["xls"]})
    assert deposit_dce(c, bid, ("DCE.zip", dce)).status_code == 202
    queue.drain_dce()
    version = c.get(f"/bids/{bid}/dce/1").json()
    assert version["status"] == "ready" and version["skipped"] == []
    kinds = {f["path"]: f["detected_kind"] for f in version["files"]}
    assert kinds == {"DCE/RC.odt": "rc", "DCE/BPU.xls": "bpu"}
    rc = next(f for f in version["files"] if f["path"] == "DCE/RC.odt")
    pages = c.get(f"/dce-files/{rc['id']}/pages").json()
    assert [p["page"] for p in pages] == [1, 2] and "vitrerie" in pages[1]["text"]
