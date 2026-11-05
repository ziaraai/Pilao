"""Company identity and pre-filled documents (US-4.5, P2-06)."""

import io
import struct
import uuid
import zlib
from typing import Any

import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import File, GeneratedDocument
from app.domain.company import vat_number
from tests.api.helpers import signed_in_client
from tests.api.test_memoir import Factory, add_reference, analyzed_bid, model  # noqa: F401
from tests.api.test_vault import confirm, deposit
from tests.conftest import FakeQueue, MemoryStorage, Outbox
from tests.documents_helpers import make_pdf

KINDS = ["dc1", "dc2", "staff_list", "equipment_list", "references_list", "planning"]


def png() -> bytes:
    """A valid 1×1 PNG (python-docx reads its header)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


def text_of(storage: MemoryStorage, db: Session, file_id: str) -> str:
    record = db.get_one(File, uuid.UUID(file_id))
    doc = Document(io.BytesIO(storage.objects[record.storage_key]))
    parts = [p.text for p in doc.paragraphs]
    parts += [c.text for t in doc.tables for row in t.rows for c in row.cells]
    parts += [p.text for s in doc.sections for p in s.header.paragraphs]
    return "\n".join(parts)


def generate(c: TestClient, bid: str, kind: str) -> dict[str, Any]:
    res = c.post(f"/bids/{bid}/documents/{kind}")
    assert res.status_code == 201, res.text
    return dict(res.json())


COMPANY = {
    "name": "Entreprise 1",
    "legal_form": "SAS",
    "address_line": "12 rue de la Paix",
    "postal_code": "69001",
    "city": "Lyon",
    "phone": "04 78 00 00 00",
    "contact_email": "appels-offres@exemple.fr",
    "signatory_name": "Abdraouf Exemple",
    "signatory_role": "Gérant",
    "brand_color": "#0B5E3C",
}


def test_company_identity_is_entered_once(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    me = c.get("/profile/company").json()
    assert me["vat_number"] == vat_number(me["siren"]) and me["phone"] is None
    saved = c.put("/profile/company", json={**COMPANY, "phone": "  "}).json()
    assert saved["city"] == "Lyon" and saved["brand_color"] == "#0B5E3C"
    assert saved["phone"] is None  # blank means "not given", never an empty string
    assert c.put("/profile/company", json={**COMPANY, "brand_color": "vert"}).status_code == 422
    assert c.put("/profile/company", json={**COMPANY, "postal_code": "6900"}).status_code == 422

    pdf = c.post("/files", files={"file": ("a.pdf", make_pdf([["x"]]), "application/pdf")})
    bad = c.put("/profile/company", json={**COMPANY, "logo_file_id": pdf.json()["id"]})
    assert bad.json()["error"]["code"] == "logo_not_image"
    logo = c.post("/files", files={"file": ("logo.png", png(), "image/png")}).json()
    ok = c.put("/profile/company", json={**COMPANY, "logo_file_id": logo["id"]})
    assert ok.json()["logo_file_id"] == logo["id"]
    unknown = c.put("/profile/company", json={**COMPANY, "logo_file_id": str(uuid.uuid4())})
    assert unknown.json()["error"]["code"] == "unknown_file"


def test_every_document_is_prefilled_from_the_profile_and_the_dce(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: Any,  # noqa: F811
    storage: MemoryStorage,
    db: Session,
) -> None:
    c = signed_in_client(make_client, outbox)
    logo = c.post("/files", files={"file": ("logo.png", png(), "image/png")}).json()
    c.put("/profile/company", json={**COMPANY, "logo_file_id": logo["id"]})
    c.put("/profile", json={"revenue_y1_cents": 125_000_000, "revenue_y2_cents": 118_000_000})
    c.post("/profile/human-resources", json={"qualification": "Agent de propreté", "count": 12})
    c.post("/profile/human-resources", json={"qualification": "Chef d'équipe", "count": 2})
    c.post("/profile/equipment", json={"name": "Autolaveuse", "category": "machine", "quantity": 3})
    add_reference(c, client_name="Mairie de Villeurbanne", title="Nettoyage des écoles", year=2024)
    urssaf = deposit(c).json()["id"]
    assert confirm(c, urssaf).json()["status"] == "valid"
    bid = analyzed_bid(c, queue)

    docs = {kind: generate(c, bid, kind) for kind in KINDS}
    assert all(d["status"] == "ready" and d["filename"].endswith(".docx") for d in docs.values())

    dc1 = text_of(storage, db, docs["dc1"]["file_id"])
    assert "Acheteur : Ville de Lyon  (source : DCE/RC.pdf p. 1)" in dc1
    assert "Objet : Nettoyage des bureaux  (source : DCE/RC.pdf p. 1)" in dc1
    assert "Téléphone : 04 78 00 00 00" in dc1 and "SIRET : " in dc1
    assert "Nom, prénom et qualité du signataire : Abdraouf Exemple, Gérant" in dc1
    assert "☐ Le candidat se présente seul" in dc1  # the company ticks, never Pilao
    assert "Entreprise 1" in dc1  # header
    assert docs["dc1"]["to_complete"] == [
        "référence donnée par l'acheteur",
        "lot(s) visé(s), le cas échéant",
        "code NAF",  # the test company was registered without the directory
        "lieu et date de signature",
    ]

    dc2 = text_of(storage, db, docs["dc2"]["file_id"])
    assert "1 250 000 € HT" in dc2 and "1 180 000 € HT" in dc2
    assert "14 personnes (détail dans la liste des moyens humains)" in dc2
    assert "Attestation de vigilance URSSAF, valable jusqu'au" in dc2
    assert "chiffre d'affaires N-3" in docs["dc2"]["to_complete"]

    staff = text_of(storage, db, docs["staff_list"]["file_id"])
    assert (
        "Agent de propreté" in staff
        and "Total" in staff
        and docs["staff_list"]["to_complete"] == []
    )
    refs = text_of(storage, db, docs["references_list"]["file_id"])
    assert "Mairie de Villeurbanne (privé)" in refs and "Nettoyage des écoles" in refs
    plan = text_of(storage, db, docs["planning"]["file_id"])
    assert "Convention collective de la propreté, annexe 7" not in plan  # no trade selected
    assert "date de démarrage" in docs["planning"]["to_complete"]

    listing = c.get(f"/bids/{bid}/documents").json()
    assert [d["kind"] for d in listing] == KINDS
    assert all(d["latest"]["id"] == docs[d["kind"]]["id"] for d in listing)


def test_nothing_is_invented_when_data_is_missing(
    make_client: Factory, outbox: Outbox, storage: MemoryStorage, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = c.post("/bids", json={"title": "Nettoyage du gymnase"}).json()["id"]  # no DCE yet
    dc1 = generate(c, bid, "dc1")
    assert dc1["to_complete"] == [
        "nom de l'acheteur",
        "référence donnée par l'acheteur",
        "lot(s) visé(s), le cas échéant",
        "forme juridique",
        "adresse du siège social",
        "code NAF",
        "téléphone (Profil > Identité)",
        "personne habilitée à engager l'entreprise",
        "lieu et date de signature",
    ]
    assert "Objet : Nettoyage du gymnase" in text_of(storage, db, dc1["file_id"])
    refs = generate(c, bid, "references_list")
    assert refs["to_complete"] == ["références de prestations similaires (Profil > Références)"]
    dc2 = generate(c, bid, "dc2")
    assert "attestations à jour (coffre-fort)" in dc2["to_complete"]
    assert "chiffre d'affaires N-1" in dc2["to_complete"]


def test_only_the_last_versions_of_a_document_are_kept(
    make_client: Factory, outbox: Outbox, storage: MemoryStorage, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = c.post("/bids", json={"title": "Nettoyage"}).json()["id"]
    before = len(storage.objects)
    ids = [generate(c, bid, "planning")["file_id"] for _ in range(4)]
    kept = db.scalars(select(GeneratedDocument.file_id)).all()
    assert sorted(str(i) for i in kept) == sorted(ids[1:])  # the oldest one is gone
    assert len(storage.objects) == before + 3
    assert db.scalar(select(func.count()).select_from(File)) == 3


def test_tenancy_isolation(
    make_client: Factory,
    outbox: Outbox,
    queue: FakeQueue,
    model: Any,  # noqa: F811
    storage: MemoryStorage,
    db: Session,
) -> None:
    a, b = signed_in_client(make_client, outbox, 1), signed_in_client(make_client, outbox, 2)
    add_reference(a, title="Référence confidentielle de A")
    bid = analyzed_bid(b, queue)
    refs = generate(b, bid, "references_list")
    assert "confidentielle de A" not in text_of(storage, db, refs["file_id"])
    assert a.get(f"/bids/{bid}/documents").status_code == 404
    assert a.post(f"/bids/{bid}/documents/dc1").status_code == 404
    assert a.get(f"/files/{refs['file_id']}").status_code == 404


def test_unknown_kind_and_authentication(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox)
    bid = c.post("/bids", json={"title": "Nettoyage"}).json()["id"]
    assert c.post(f"/bids/{bid}/documents/memoir_docx").json()["error"]["code"] == (
        "unknown_document"
    )
    anon = make_client()
    assert anon.get(f"/bids/{bid}/documents").status_code == 401
    assert anon.get("/profile/company").status_code == 401


@pytest.mark.parametrize("trades", [["nettoyage_locaux"], ["vitrerie"]])
def test_cleaning_companies_get_the_staff_takeover_step(
    make_client: Factory, outbox: Outbox, storage: MemoryStorage, db: Session, trades: list[str]
) -> None:
    c = signed_in_client(make_client, outbox)
    assert c.put("/profile", json={"trades": trades}).status_code == 200
    bid = c.post("/bids", json={"title": "Nettoyage"}).json()["id"]
    plan = text_of(storage, db, generate(c, bid, "planning")["file_id"])
    assert "Convention collective de la propreté, annexe 7" in plan
