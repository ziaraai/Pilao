"""Text extraction from PDF and DOCX, keeping page numbers and headings.

Scanned PDFs (almost no text layer) are reported, not guessed: OCR arrives with the DCE
pipeline (P1-09) and these documents can then be re-indexed.
"""

import re
from dataclasses import dataclass
from typing import BinaryIO

import pdfplumber
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

MAX_PAGES = 600
MAX_CHARS = 8_000_000
MIN_CHARS_PER_PAGE = 40  # below this a page is considered image-only

_HEADING_RE = re.compile(
    r"^(?:(?i:ARTICLE|CHAPITRE|TITRE|PARTIE|SECTION)\s+[\dIVXL]+\b.*"
    r"|\d{1,2}(?:\.\d{1,2}){0,3}[\.\)]?\s+[A-ZÉÈÀÂÊÎÔÛÇ][^\n]{2,90})$"
)


class ExtractionError(Exception):
    """User-facing (French) reason why a document cannot be indexed."""


@dataclass(frozen=True)
class Block:
    kind: str  # "heading" | "paragraph"
    text: str
    page: int | None  # None for formats without pages (DOCX)


def looks_like_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 110 or line.endswith((",", ";")):
        return False
    if _HEADING_RE.match(line):
        return True
    letters = [c for c in line if c.isalpha()]
    return len(line) <= 70 and len(letters) >= 4 and all(c.isupper() for c in letters)


def extract_pdf(fileobj: BinaryIO) -> list[Block]:
    blocks: list[Block] = []
    total_chars = 0
    low_text_pages = 0
    try:
        with pdfplumber.open(fileobj) as pdf:  # type: ignore[arg-type]
            pages = pdf.pages
            if len(pages) > MAX_PAGES:
                raise ExtractionError(
                    f"Document trop long ({len(pages)} pages, {MAX_PAGES} maximum)."
                )
            for number, page in enumerate(pages, start=1):
                text = page.extract_text() or ""
                if len(text.strip()) < MIN_CHARS_PER_PAGE:
                    low_text_pages += 1
                total_chars += len(text)
                if total_chars > MAX_CHARS:
                    raise ExtractionError("Document trop volumineux à indexer.")
                # Paragraphs end on blank lines only: lines inside one are re-joined (and
                # de-hyphenated) by _split_heading_lines, which also isolates heading lines.
                for para in re.split(r"\n\s*\n", text):
                    for line_block in _split_heading_lines(para):
                        blocks.append(Block(line_block[0], line_block[1], number))
            page_count = len(pages)
    except ExtractionError:
        raise
    except Exception as exc:
        raise ExtractionError("Impossible de lire ce PDF (fichier corrompu ou protégé).") from exc
    if page_count and low_text_pages / page_count > 0.8:
        raise ExtractionError(
            "Ce PDF est un scan sans texte. La reconnaissance de caractères (OCR) "
            "n'est pas encore disponible : déposez une version texte."
        )
    return blocks


def _split_heading_lines(paragraph: str) -> list[tuple[str, str]]:
    """Separate heading lines from body text inside one extracted paragraph."""
    out: list[tuple[str, str]] = []
    body: list[str] = []
    for line in paragraph.split("\n"):
        if looks_like_heading(line):
            if body:
                out.append(("paragraph", _join(body)))
                body = []
            out.append(("heading", line.strip()))
        elif line.strip():
            body.append(line.strip())
    if body:
        out.append(("paragraph", _join(body)))
    return [(k, t) for k, t in out if t]


def _join(lines: list[str]) -> str:
    # Re-join words hyphenated by the line wrap ("entre-\ntien" -> "entretien").
    text = " ".join(lines)
    return re.sub(r"(\w)- (?=[a-zàâçéèêëîïôûù])", r"\1", text)


# « 1 – PRESENTATION », « 2.1 - Description », « II. Annexes »: a number, then a separator.
# « 3 auto laveuses » (a number, no separator) is a list item, not a title.
NUMBERED_TITLE = re.compile(r"^(?:\d{1,2}(?:\.\d{1,2})*|[IVX]{1,5})\s*[-–—.)]\s*\S")


def _bold(para: Paragraph) -> bool:
    runs = [r for r in para.runs if r.text.strip()]
    style_bold = bool(para.style is not None and para.style.font.bold)
    return bool(runs) and all(
        r.bold or (r.bold is None and (style_bold or bool(r.style and r.style.font.bold)))
        for r in runs
    )


def _looks_like_title(para: Paragraph, text: str) -> bool:
    """A title written without a heading style (memoirs typed in LibreOffice, ADR-037): a
    short numbered line, or a short line all in bold. Never a sentence."""
    if len(text) > 120 or text.endswith((".", ";", ",")):
        return False
    if NUMBERED_TITLE.match(text):
        return True
    return len(text) <= 80 and _bold(para)


def extract_docx(fileobj: BinaryIO) -> list[Block]:
    try:
        doc = Document(fileobj)
    except Exception as exc:
        raise ExtractionError("Impossible de lire ce document Word.") from exc
    blocks: list[Block] = []
    total = 0
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name if para.style is not None else "") or ""
            is_heading = style.lower().startswith(("heading", "titre")) or style == "Title"
            is_heading = is_heading or _looks_like_title(para, text)
            blocks.append(Block("heading" if is_heading else "paragraph", text, None))
            total += len(text)
        elif child.tag.endswith("}tbl"):
            table = Table(child, doc)
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    row_text = " | ".join(dict.fromkeys(cells))
                    blocks.append(Block("paragraph", row_text, None))
                    total += len(row_text)
                if total > MAX_CHARS:
                    raise ExtractionError("Document trop volumineux à indexer.")
        if total > MAX_CHARS:
            raise ExtractionError("Document trop volumineux à indexer.")
    if not blocks:
        raise ExtractionError("Ce document ne contient aucun texte.")
    return blocks
