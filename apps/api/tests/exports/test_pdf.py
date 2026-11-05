"""Real LibreOffice conversion (installed in CI and in the worker image)."""

import io
import re
import shutil
from datetime import datetime

import pdfplumber
import pytest

from app.exports.memoir_docx import Chapter, MemoirExportData, build_memoir
from app.exports.pdf import LibreOfficeConverter, PdfUnavailable

LONG = "\n\n".join(f"Paragraphe {i} : " + "texte de méthodologie détaillé " * 40 for i in range(10))


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice is not installed here")
def test_the_pdf_contents_show_the_real_page_of_each_chapter() -> None:
    data = MemoirExportData(
        company="Propreté Lyonnaise",
        tender_title="Nettoyage des bureaux",
        buyer="Ville de Lyon",
        reference=None,
        lot=None,
        version=1,
        exported_at=datetime(2026, 11, 5, 10, 0),
        chapters=[
            Chapter("1. Moyens", f"## 1. Moyens\n\n{LONG}"),
            Chapter("2. Méthodologie", f"## 2. Méthodologie\n\n{LONG}"),
        ],
    )
    pdf = LibreOfficeConverter("soffice", 120).convert(build_memoir(data).to_bytes())
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        pages = [p.extract_text() or "" for p in doc.pages]
    contents = pages[1]
    listed = {
        m.group(1): int(m.group(2))
        for m in re.finditer(r"^(\d\. \w+)[ .]*?(\d+)$", contents, re.MULTILINE)
    }
    starts = {
        title: next(i + 1 for i, text in enumerate(pages[2:], start=2) if f"\n{title}\n" in text)
        for title in ("1. Moyens", "2. Méthodologie")
    }
    assert listed == starts and starts["2. Méthodologie"] > starts["1. Moyens"] >= 3


def test_a_missing_libreoffice_is_a_clear_error() -> None:
    with pytest.raises(PdfUnavailable, match="LibreOffice n'est pas installé"):
        LibreOfficeConverter("soffice-introuvable", 5).convert(b"PK")
