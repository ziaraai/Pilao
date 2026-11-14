"""Export of the memoir: Word, PDF, complete ZIP, with warnings first (US-4.6, P2-07)."""

import io
import uuid
import zipfile
from typing import Any

import pytest
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import File
from app.exports.pdf import PdfUnavailable
from tests.api.helpers import signed_in_client
from tests.api.test_documents import COMPANY, png
from tests.api.test_memoir_drafting import (  # noqa: F401 - the model fixture
    FOUR,
    Factory,
    Sections,
    WriterModel,
    drafted,
    latest,
    model,
    prepared,
    quote_everything,
    section,
)
from tests.api.test_vault import confirm, day, deposit
from tests.conftest import FakeQueue, MemoryStorage, Outbox


class FakeConverter:
    def __init__(self) -> None:
        self.calls = 0
        self.error: Exception | None = None

    def convert(self, docx: bytes) -> bytes:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert docx.startswith(b"PK")  # a real Word file was handed over
        return b"%PDF-1.7 fake"


@pytest.fixture
def converter() -> FakeConverter:
    return FakeConverter()


def export(c: TestClient, memoir_id: str, fmt: str, ack: bool = True) -> Any:
    return c.post(
        f"/memoirs/{memoir_id}/exports", json={"format": fmt, "acknowledge_warnings": ack}
    )


def exported(
    c: TestClient, queue: FakeQueue, converter: FakeConverter, memoir_id: str, fmt: str
) -> dict[str, Any]:
    res = export(c, memoir_id, fmt)
    assert res.status_code == 202, res.text
    assert res.json()["status"] == "pending"
    queue.drain_exports(converter)
    return dict(c.get(f"/generated-documents/{res.json()['id']}").json())


def content(storage: MemoryStorage, db: Session, file_id: str) -> bytes:
    return storage.objects[db.get_one(File, uuid.UUID(file_id)).storage_key]


def test_word_export_has_cover_contents_chapters_and_correspondence(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: WriterModel,  # noqa: F811
    converter: FakeConverter,
    storage: MemoryStorage,
    db: Session,
) -> None:
    model.matrix = quote_everything
    c = signed_in_client(make_client, outbox)
    logo = c.post("/files", files={"file": ("logo.png", png(), "image/png")}).json()
    c.put("/profile/company", json={**COMPANY, "logo_file_id": logo["id"]})
    m = drafted(c, queue)

    check = c.get(f"/memoirs/{m['id']}/export-check").json()
    assert check["warnings"] == ["2 « [À COMPLÉTER] » restent dans : 1. Moyens, 2. Méthodologie."]
    assert [x["items"] for x in check["to_complete"]] == [["nombre d'agents affectés au site"]] * 2
    refused = export(c, m["id"], "docx", ack=False)
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "export_needs_confirmation"

    doc = exported(c, queue, converter, m["id"], "docx")
    assert doc["status"] == "ready" and doc["filename"].endswith("v1.docx")
    assert doc["warnings"] == check["warnings"]  # what the user accepted is kept
    assert doc["to_complete"] == ["nombre d'agents affectés au site"]
    assert latest(c, m["id"])["status"] == "exported" and converter.calls == 0

    data = content(storage, db, doc["file_id"])
    word = Document(io.BytesIO(data))
    texts = [p.text for p in word.paragraphs]
    assert "Mémoire technique" in texts and "Nettoyage des bureaux" in texts
    assert "Acheteur : Ville de Lyon" in texts and "Entreprise 1" in texts
    assert "Sommaire" in texts and "1. Moyens\t1" in texts  # page computed on layout
    headings = [p.text for p in word.paragraphs if p.style.name == "Heading 1"]
    assert headings == [
        "1. Moyens",
        "2. Méthodologie",
        "Correspondance avec les exigences du CCTP",
    ]
    todo_runs = [r for p in word.paragraphs for r in p.runs if r.text.startswith("[À COMPLÉTER")]
    assert todo_runs and all(r.font.highlight_color == WD_COLOR_INDEX.YELLOW for r in todo_runs)
    correspondence = word.tables[-1]
    assert [[cell.text for cell in row.cells] for row in correspondence.rows][1:] == [
        ["CCTP-1", "Nettoyage quotidien des bureaux avant 8h", "2. Méthodologie"],
        ["CCTP-2", "Vitrerie intérieure trimestrielle", "2. Méthodologie"],
    ]
    xml = word.element.xml
    assert 'w:name="_Toc1"' in xml and "PAGEREF _Toc2" in xml
    assert word.sections[0].different_first_page_header_footer  # a plain cover page
    assert "Entreprise 1 — Nettoyage des bureaux" in word.sections[0].header.paragraphs[0].text
    assert word.inline_shapes  # the logo
    assert b"updateFields" in zipfile.ZipFile(io.BytesIO(data)).read("word/settings.xml")


def test_export_needs_a_drafted_memoir(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: WriterModel,  # noqa: F811
) -> None:
    c = signed_in_client(make_client, outbox)
    m = prepared(c, queue)
    assert export(c, m["id"], "docx").json()["error"]["code"] == "memoir_not_generated"
    c.post(f"/memoirs/{m['id']}/generate")
    assert export(c, m["id"], "docx").json()["error"]["code"] == "memoir_busy"


def test_missing_requirements_and_an_outdated_matrix_are_warned(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: WriterModel,  # noqa: F811
) -> None:
    def strict(sections: Sections, refs: list[str]) -> list[dict[str, Any]]:
        return [
            (
                {"requirement_ref": r, "status": "missing"}
                if r == "CCTP-3"
                else quote_everything(sections, [r])[0]
            )
            for r in refs
        ]

    model.extra, model.matrix = {"requirements": FOUR}, strict
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    check = c.get(f"/memoirs/{m['id']}/export-check").json()
    assert check["missing_requirements"] == [{"ref": "CCTP-3", "text": "Produits écolabellisés"}]
    assert "1 exigence du CCTP absente du mémoire : CCTP-3." in check["warnings"]

    first = section(m, "1. Moyens")
    c.put(
        f"/memoir-sections/{first['id']}",
        json={"body_md": "Texte revu.", "base_revision": first["revision"]},
    )
    check = c.get(f"/memoirs/{m['id']}/export-check").json()
    assert "La matrice de conformité date d'avant vos dernières modifications." in check["warnings"]
    assert [x["title"] for x in check["to_complete"]] == ["2. Méthodologie"]


def test_pdf_export_and_its_failure(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: WriterModel,  # noqa: F811
    converter: FakeConverter,
    storage: MemoryStorage,
    db: Session,
) -> None:
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    pdf = exported(c, queue, converter, m["id"], "pdf")
    assert pdf["status"] == "ready" and pdf["filename"].endswith(".pdf")
    assert content(storage, db, pdf["file_id"]) == b"%PDF-1.7 fake"
    assert db.get_one(File, uuid.UUID(pdf["file_id"])).mime == "application/pdf"

    converter.error = PdfUnavailable("La conversion PDF a échoué.")
    failed = exported(c, queue, converter, m["id"], "pdf")
    assert failed["status"] == "error" and failed["file_id"] is None
    assert failed["error"] == (
        "La conversion PDF a échoué. Téléchargez le Word et enregistrez-le en PDF depuis Word."
    )
    listed = c.get(f"/memoirs/{m['id']}/exports").json()
    assert [d["status"] for d in listed] == ["error", "ready"]


def test_zip_bundle_holds_the_whole_folder_with_valid_attestations_only(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: WriterModel,  # noqa: F811
    converter: FakeConverter,
    storage: MemoryStorage,
    db: Session,
) -> None:
    c = signed_in_client(make_client, outbox)
    valid = deposit(c, name="urssaf.pdf").json()["id"]
    assert confirm(c, valid).json()["status"] == "valid"
    expired = deposit(c, name="vieux-kbis.pdf").json()["id"]
    assert confirm(c, expired, kind="kbis", valid_until=day(-3)).json()["status"] == "expired"
    m = drafted(c, queue)
    converter.error = PdfUnavailable("LibreOffice n'est pas installé sur le serveur.")
    bundle = exported(c, queue, converter, m["id"], "zip")
    assert bundle["status"] == "ready" and bundle["filename"].startswith("Dossier de réponse")

    archive = zipfile.ZipFile(io.BytesIO(content(storage, db, bundle["file_id"])))
    names = sorted(archive.namelist())
    assert names == sorted(
        [
            "01 - Mémoire technique.docx",
            "02 - Pièces administratives/DC1 — Lettre de candidature.docx",
            "02 - Pièces administratives/DC2 — Déclaration du candidat.docx",
            "02 - Pièces administratives/Liste des moyens humains.docx",
            "02 - Pièces administratives/Liste des moyens matériels.docx",
            "02 - Pièces administratives/Liste des références.docx",
            "02 - Pièces administratives/Trame de planning.docx",
            "03 - Attestations/Attestation de vigilance URSSAF - urssaf.pdf",
            "LISEZ-MOI.txt",
        ]
    )
    readme = archive.read("LISEZ-MOI.txt").decode("utf-8-sig")
    assert "BROUILLON À RELIRE" in readme
    assert "2 « [À COMPLÉTER] » restent dans : 1. Moyens, 2. Méthodologie." in readme
    assert "PDF non joint (LibreOffice n'est pas installé sur le serveur.)" in readme
    assert "- Extrait Kbis" in readme.split("Attestations non jointes")[1]  # expired: left out

    converter.error = None
    again = exported(c, queue, converter, m["id"], "zip")
    archive = zipfile.ZipFile(io.BytesIO(content(storage, db, again["file_id"])))
    assert archive.read("01 - Mémoire technique.pdf") == b"%PDF-1.7 fake"


def test_an_unavailable_queue_is_reported(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: WriterModel,  # noqa: F811
) -> None:
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    queue.down = True
    doc = export(c, m["id"], "docx").json()
    assert doc["status"] == "error" and doc["error"] == (
        "File d'attente indisponible : relancez l'export."
    )


def test_tenancy_isolation(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: WriterModel,  # noqa: F811
    converter: FakeConverter,
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    m = drafted(b, queue)
    doc = exported(b, queue, converter, m["id"], "docx")
    assert a.get(f"/memoirs/{m['id']}/export-check").status_code == 404
    assert export(a, m["id"], "docx").status_code == 404
    assert a.get(f"/memoirs/{m['id']}/exports").status_code == 404
    assert a.get(f"/generated-documents/{doc['id']}").status_code == 404
    assert a.get(f"/files/{doc['file_id']}/download-url").status_code == 404


def test_requires_authentication(make_client: Factory) -> None:
    anon = make_client()
    some = uuid.uuid4()
    assert anon.get(f"/memoirs/{some}/export-check").status_code == 401
    assert anon.post(f"/memoirs/{some}/exports", json={"format": "docx"}).status_code == 401
    assert anon.get(f"/generated-documents/{some}").status_code == 401


def test_chapter_titles_keep_the_bold_of_their_style() -> None:
    from datetime import datetime

    from app.exports.memoir_docx import Chapter, MemoirExportData, build_memoir

    data = MemoirExportData(
        company="ACME",
        tender_title="Nettoyage",
        buyer=None,
        reference=None,
        lot=None,
        version=1,
        exported_at=datetime(2026, 11, 5),
        chapters=[Chapter("1. Moyens", "## 1. Moyens\n\nTexte **gras** et normal.")],
    )
    word = Document(io.BytesIO(build_memoir(data).to_bytes()))
    title = next(p for p in word.paragraphs if p.text == "1. Moyens")
    assert all(r.bold is None for r in title.runs)  # inherited from Heading 1 (bold)
    body = next(p for p in word.paragraphs if p.text.startswith("Texte"))
    assert [(r.text, r.bold) for r in body.runs] == [
        ("Texte ", None),
        ("gras", True),
        (" et normal.", None),
    ]


def test_the_font_imposed_by_the_rc_is_applied() -> None:
    from datetime import datetime

    from docx.shared import Pt

    from app.exports.memoir_docx import Chapter, MemoirExportData, build_memoir

    data = MemoirExportData(
        company="ACME",
        tender_title="Nettoyage",
        buyer=None,
        reference=None,
        lot=None,
        version=1,
        exported_at=datetime(2026, 11, 5),
        chapters=[Chapter("1. Moyens", "## 1. Moyens\n\n| A | B |\n|---|---|\n| x | y |")],
        font="Times New Roman",
        font_size=11,
    )
    word = Document(io.BytesIO(build_memoir(data).to_bytes()))
    normal = word.styles["Normal"].font
    assert (normal.name, normal.size) == ("Times New Roman", Pt(11))
    assert word.styles["Heading 1"].font.name == "Times New Roman"
    assert word.styles["Heading 3"].font.size >= Pt(11)  # never smaller than the body
    xml = word.styles.element.xml
    assert 'w:ascii="Times New Roman"' in xml and "Arial" not in xml
    default = build_memoir(MemoirExportData(**{**vars(data), "font": None, "font_size": None}))
    assert default.doc.styles["Normal"].font.name == "Arial"
    assert default.doc.styles["Normal"].font.size == Pt(10.5)


def test_the_rc_font_drives_the_export_and_the_page_estimate(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: WriterModel,  # noqa: F811
    converter: FakeConverter,
    storage: MemoryStorage,
    db: Session,
) -> None:
    from docx.shared import Pt

    from tests.api.test_analysis import SRC_RC

    model.extra = {
        "memoir_requirements": {
            "imposed_outline": ["1. Moyens", "2. Méthodologie"],
            "max_pages": 1,
            "format_constraints": "1 page maximum. Police Times New Roman, taille 12.",
            "source": {"file": SRC_RC, "page": 2},
        }
    }
    model.words = 170  # about 420 words: 1 page in the default 10.5 pt, 2 pages in 12 pt
    c = signed_in_client(make_client, outbox)
    m = drafted(c, queue)
    assert (m["estimated_pages"], m["max_pages"]) == (2, 1)
    assert m["word_budget"] == int(1 * 383 * 0.9)  # the plan already counts 12 pt pages
    assert m["page_warning"].startswith("Environ 2 pages pour 1 autorisées")
    check = c.get(f"/memoirs/{m['id']}/export-check").json()
    assert "Environ 2 pages pour 1 autorisées." in check["warnings"]
    doc = exported(c, queue, converter, m["id"], "docx")
    word = Document(io.BytesIO(content(storage, db, doc["file_id"])))
    normal = word.styles["Normal"].font
    assert (normal.name, normal.size) == ("Times New Roman", Pt(12))
