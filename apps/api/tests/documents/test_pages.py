import io
import shutil
import time

import pytest
from openpyxl import Workbook
from PIL import Image

from app.documents.ocr import OcrUnavailable, TesseractOcr
from app.documents.pages import extract_pages
from app.domain.dce import kind_from_content, kind_from_filename
from app.domain.filetypes import DOCX, PDF, PNG, XLSX
from tests.documents_helpers import make_docx, make_mixed_pdf, make_pdf, make_scanned_pdf

needs_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract not installed"
)


class NoOcr:
    def image_to_text(self, image: Image.Image) -> str:
        raise OcrUnavailable("absent")


class CountingOcr:
    def __init__(self) -> None:
        self.calls = 0

    def image_to_text(self, image: Image.Image) -> str:
        self.calls += 1
        return "TEXTE RECONNU PAR OCR " * 5


def test_text_pdf_pages_keep_their_numbers_and_skip_ocr() -> None:
    ocr = CountingOcr()
    pdf = make_pdf(
        [
            ["Article 1 - Objet du marche", "Nettoyage des locaux de la mairie"],
            [
                "Article 2 - Duree",
                "Le marche est conclu pour trois ans a compter de la notification",
            ],
        ]
    )
    result = extract_pages(io.BytesIO(pdf), PDF.mime, ocr)
    assert result.status == "ready" and [p.page for p in result.pages] == [1, 2]
    assert "trois ans" in result.pages[1].text and not result.ocr_used
    assert ocr.calls == 0  # pages with a text layer never go through OCR


def test_scanned_pages_go_through_ocr_only_when_needed() -> None:
    ocr = CountingOcr()
    result = extract_pages(io.BytesIO(make_scanned_pdf(["Page scannee"], pages=3)), PDF.mime, ocr)
    assert ocr.calls == 3 and result.ocr_used and result.status == "ready"
    assert all(p.ocr_used and "OCR" in p.text for p in result.pages)


def test_text_drawn_as_images_goes_through_ocr_too() -> None:
    """A CCTB « fiche d'intervention » (25/11): the header is text, but each description is a
    small image of text. The page has enough text not to look scanned, yet its lines to price
    are only readable by OCR."""
    header = [
        "CCTB - Rue de l'orphelinat - 42100 SAINT ETIENNE",
        "Fiche d'intervention etablie depuis le devis n DE36594",
        "Numero Description Qte Unite Rapport d'intervention",
    ]
    drawn = ["Nettoyage et cristallisation du sol", "Nettoyage de fin de chantier"]
    ocr = CountingOcr()
    result = extract_pages(io.BytesIO(make_mixed_pdf(header, drawn)), PDF.mime, ocr)
    assert ocr.calls == 1 and result.pages[0].ocr_used
    # a page with a logo only (one image) keeps its text layer
    ocr = CountingOcr()
    logo_only = make_mixed_pdf([*header, "Page sans libelle en image"], ["LOGO"])
    assert extract_pages(io.BytesIO(logo_only), PDF.mime, ocr).pages[0].ocr_used is False
    assert ocr.calls == 0


@needs_tesseract
def test_real_tesseract_reads_the_descriptions_drawn_as_images() -> None:
    header = [
        "CCTB - Rue de l'orphelinat - 42100 SAINT ETIENNE",
        "Fiche d'intervention etablie depuis le devis n DE36594",
        "Numero Description Qte Unite Rapport d'intervention",
    ]
    drawn = ["Nettoyage et cristallisation du sol", "Traitement et valorisation des dechets"]
    page = extract_pages(io.BytesIO(make_mixed_pdf(header, drawn)), PDF.mime, TesseractOcr()).pages[
        0
    ]
    assert "cristallisation" in page.text and "valorisation" in page.text
    assert "DE36594" in page.text  # the text layer's facts are still there


def test_missing_ocr_engine_is_reported_not_fatal() -> None:
    result = extract_pages(io.BytesIO(make_scanned_pdf(["x"])), PDF.mime, NoOcr())
    assert result.status == "ocr_unavailable" and len(result.pages) == 1
    assert (
        extract_pages(io.BytesIO(make_scanned_pdf(["x"])), PDF.mime, None).status
        == "ocr_unavailable"
    )


@needs_tesseract
def test_real_tesseract_reads_a_scanned_french_page() -> None:
    lines = [
        "REGLEMENT DE LA CONSULTATION",
        "Date limite de remise des offres :",
        "15 décembre 2026 à 12h00",
    ]
    pdf = make_scanned_pdf(lines)
    started = time.monotonic()
    result = extract_pages(io.BytesIO(pdf), PDF.mime, TesseractOcr())
    elapsed = time.monotonic() - started
    text = result.pages[0].text
    assert result.ocr_used and "REGLEMENT DE LA CONSULTATION" in text
    assert "décembre 2026" in text  # French accents survive (lang=fra)
    assert kind_from_content(text).kind == "rc"
    assert elapsed < 20  # one A4 page at 200 dpi


def test_docx_is_one_unpaginated_page_with_tables() -> None:
    data = make_docx(
        [("Heading 1", "Acte d'engagement"), ("Normal", "Le titulaire s'engage.")],
        table=[["Lot", "Montant"], ["1", "12 000"]],
    )
    result = extract_pages(io.BytesIO(data), DOCX.mime, None)
    assert not result.paginated and len(result.pages) == 1
    assert "s'engage" in result.pages[0].text and "1 | 12 000" in result.pages[0].text


def test_spreadsheet_is_one_page_per_sheet() -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "BPU"
    ws.append(["Désignation", "Unité", "Prix"])
    ws.append(["Nettoyage bureaux", "m²", None])
    wb.create_sheet("Notes").append(["À remplir par le candidat"])
    out = io.BytesIO()
    wb.save(out)
    result = extract_pages(io.BytesIO(out.getvalue()), XLSX.mime, None)
    assert [p.page for p in result.pages] == [1, 2]
    assert (
        result.pages[0].text.startswith("Feuille : BPU")
        and "Nettoyage bureaux | m²" in result.pages[0].text
    )


def test_image_and_corrupt_inputs() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "white").save(buf, format="PNG")
    assert extract_pages(io.BytesIO(buf.getvalue()), PNG.mime, CountingOcr()).ocr_used
    assert extract_pages(io.BytesIO(buf.getvalue()), PNG.mime, NoOcr()).status == "ocr_unavailable"
    bad = extract_pages(io.BytesIO(b"%PDF-1.4 broken"), PDF.mime, None)
    assert bad.status == "error" and "illisible" in (bad.error or "")
    assert extract_pages(io.BytesIO(b"x"), "application/zip", None).status == "unsupported"


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("RC.pdf", "rc"),
        ("02 - Règlement de consultation.pdf", "rc"),
        ("CCAP_lot1.pdf", "ccap"),
        ("CCTP nettoyage.docx", "cctp"),
        ("ATTRI1.pdf", "ae"),
        ("AE lot 2.pdf", "ae"),
        ("BPU.xlsx", "bpu"),
        ("26020M_BPM_prestations_entretien_bat_sportifs.xlsx", "bpu"),  # prix mixtes
        ("Bordereau des prix mixtes.pdf", "bpu"),
        ("DPGF.xlsx", "dpgf"),
        ("DQE.xlsx", "dqe"),
        ("Annexe 3 au CCTP - surfaces.pdf", "annex"),
        ("Plans RDC.pdf", "annex"),
        ("Cadre de réponse technique.docx", "annex"),
        ("piece3.pdf", "other"),
        ("ARCHIVE/sous dossier/rc final.pdf", "rc"),
    ],
)
def test_kind_from_filename(name: str, kind: str) -> None:
    assert kind_from_filename(name).kind == kind


def test_kind_from_content_uses_the_title_not_later_mentions() -> None:
    cctp = "CAHIER DES CLAUSES TECHNIQUES PARTICULIÈRES\nVoir le règlement de la consultation (RC)."
    assert kind_from_content(cctp).kind == "cctp"
    assert kind_from_content("Bordereau des prix unitaires - lot 1").kind == "bpu"
    assert kind_from_content("BPM (Bordereau des Prix Mixtes)").kind == "bpu"
    assert kind_from_content("Lettre d'information").source == "none"
