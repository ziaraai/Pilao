"""Page-by-page text of DCE pieces (US-3.1 CA3), with OCR for scanned pages.

Every page keeps its number so that each extracted fact can cite "file + page"
(CLAUDE.md §5.2). DOCX has no pages: its text is stored as page 1 and ``paginated`` is False.
"""

import io
from dataclasses import dataclass, field
from typing import BinaryIO

import pdfplumber
from docx import Document
from openpyxl import load_workbook
from PIL import Image

from app.documents.convert import ConversionUnavailable, readable_form
from app.documents.ocr import OcrEngine, OcrUnavailable
from app.domain.filetypes import (
    DOCX,
    JPEG,
    PDF,
    PNG,
    SHEETS_TO_CONVERT,
    TEXT_TO_CONVERT,
    XLSX,
)

MAX_PAGES = 600
MAX_OCR_PAGES = 200  # per file: a 300-page DCE is rarely more than a few scanned pieces
MIN_TEXT_CHARS = 40  # a page with less text is treated as scanned
OCR_RESOLUTION = 200
MAX_SHEET_ROWS = 5000
MAX_CHARS = 5_000_000


@dataclass
class PageText:
    page: int
    text: str
    ocr_used: bool = False


@dataclass
class Extraction:
    pages: list[PageText] = field(default_factory=list)
    status: str = "ready"  # ready | error | unsupported | ocr_unavailable
    error: str | None = None
    paginated: bool = True

    @property
    def ocr_used(self) -> bool:
        return any(p.ocr_used for p in self.pages)


def _ocr(ocr: OcrEngine | None, image: Image.Image) -> str | None:
    """Text of an image, or None if no OCR engine can run."""
    if ocr is None:
        return None
    try:
        return ocr.image_to_text(image).strip()
    except OcrUnavailable:
        return None


def _pdf(fileobj: BinaryIO, ocr: OcrEngine | None) -> Extraction:
    result = Extraction()
    ocr_budget, ocr_missing, total = MAX_OCR_PAGES, False, 0
    try:
        with pdfplumber.open(fileobj) as pdf:  # type: ignore[arg-type]
            if len(pdf.pages) > MAX_PAGES:
                return Extraction(status="error", error=f"Plus de {MAX_PAGES} pages.")
            for number, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                used = False
                if len(text) < MIN_TEXT_CHARS:
                    if ocr_budget > 0:
                        ocr_budget -= 1
                        image = page.to_image(resolution=OCR_RESOLUTION).original
                        read = _ocr(ocr, image)
                        if read is None:
                            ocr_missing = True
                        elif len(read) > len(text):
                            text, used = read, True
                    else:
                        ocr_missing = True
                page.close()  # frees the page's parsed objects: memory stays flat on long PDFs
                total += len(text)
                if total > MAX_CHARS:
                    return Extraction(status="error", error="Document trop volumineux.")
                result.pages.append(PageText(number, text, used))
    except Exception:  # noqa: BLE001 - corrupt or encrypted PDF
        return Extraction(status="error", error="PDF illisible (corrompu ou protégé).")
    if ocr_missing:
        result.status = "ocr_unavailable"
    return result


def _docx(fileobj: BinaryIO) -> Extraction:
    try:
        doc = Document(fileobj)
    except Exception:  # noqa: BLE001
        return Extraction(status="error", error="Document Word illisible.")
    parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(dict.fromkeys(cells)))
    text = "\n".join(parts)[:MAX_CHARS]
    return Extraction(pages=[PageText(1, text)], paginated=False)


def _xlsx(fileobj: BinaryIO) -> Extraction:
    """One "page" per sheet: BPU, DPGF and DQE are spreadsheets."""
    try:
        wb = load_workbook(fileobj, read_only=True, data_only=True)
    except Exception:  # noqa: BLE001
        return Extraction(status="error", error="Classeur Excel illisible.")
    result, total = Extraction(), 0
    try:
        for number, ws in enumerate(wb.worksheets, start=1):
            lines = [f"Feuille : {ws.title}"]
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i >= MAX_SHEET_ROWS:
                    lines.append("[… lignes suivantes non lues]")
                    break
                cells = [str(v).strip() for v in row if v is not None and str(v).strip()]
                if cells:
                    lines.append(" | ".join(cells))
            text = "\n".join(lines)
            total += len(text)
            if total > MAX_CHARS:
                return Extraction(status="error", error="Classeur trop volumineux.")
            result.pages.append(PageText(number, text))
    except Exception:  # noqa: BLE001
        return Extraction(status="error", error="Classeur Excel illisible.")
    finally:
        wb.close()
    return result


def _image(fileobj: BinaryIO, ocr: OcrEngine | None) -> Extraction:
    try:
        image = Image.open(fileobj)
        image.load()
    except Exception:  # noqa: BLE001
        return Extraction(status="error", error="Image illisible.")
    read = _ocr(ocr, image)
    if read is None:
        return Extraction(pages=[PageText(1, "")], status="ocr_unavailable")
    return Extraction(pages=[PageText(1, read, True)])


def extract_pages(fileobj: BinaryIO, mime: str, ocr: OcrEngine | None) -> Extraction:
    fileobj.seek(0)
    to_convert = {t.mime: t for t in (*TEXT_TO_CONVERT, *SHEETS_TO_CONVERT)}
    if mime in to_convert:  # LibreOffice / Office 97-2003: a PDF keeps the pages (ADR-034)
        try:
            converted, kind = readable_form(fileobj.read(), to_convert[mime], text_target="pdf")
        except ConversionUnavailable as exc:
            return Extraction(status="error", error=f"Lecture impossible : {exc}")
        fileobj, mime = io.BytesIO(converted), kind.mime
    data: BinaryIO = io.BytesIO(fileobj.read()) if mime != PDF.mime else fileobj
    if mime == PDF.mime:
        return _pdf(data, ocr)
    if mime == DOCX.mime:
        return _docx(data)
    if mime == XLSX.mime:
        return _xlsx(data)
    if mime in (PNG.mime, JPEG.mime):
        return _image(data, ocr)
    return Extraction(status="unsupported")
