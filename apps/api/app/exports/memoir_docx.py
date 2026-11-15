"""The technical memoir in Word (US-4.6 CA1).

Cover page with the logo, automatic table of contents, one chapter per section, a
correspondence table with the CCTP requirements, header and footer with page numbers.

The table of contents is one line per chapter with a PAGEREF field to a bookmark on the
chapter title: LibreOffice computes those page references while laying out the PDF, and
Word refreshes them on opening (the file asks it to). A Word TOC field was tried first:
LibreOffice turns it into a static index and prints its cached page numbers (ADR-022).
"""

import io
from dataclasses import dataclass, field
from datetime import datetime

from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.shared import Cm, Pt, RGBColor
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from app.exports.dc_forms import french_date
from app.exports.docx_builder import (
    GREY,
    DocBuilder,
    _paragraph_borders,
    _shade,
    set_widths,
    tint,
)


@dataclass(frozen=True)
class Chapter:
    title: str
    markdown: str | None


@dataclass(frozen=True)
class RequirementRow:
    ref: str
    text: str
    chapter: str | None


@dataclass
class MemoirExportData:
    company: str
    tender_title: str
    buyer: str | None
    reference: str | None
    lot: str | None
    version: int
    exported_at: datetime  # Paris time
    chapters: list[Chapter]
    requirements: list[RequirementRow] = field(default_factory=list)
    brand_color: str | None = None
    logo: bytes | None = None
    font: str | None = None  # imposed by the RC (« Times New Roman, taille 11 »)
    font_size: float | None = None
    # the company's own coordinates for the cover (only what its profile holds)
    company_lines: list[str] = field(default_factory=list)
    signatory: str | None = None


def _complex_field(paragraph: Paragraph, instruction: str, cached: str) -> None:
    def run_with(element: BaseOxmlElement) -> None:
        run = OxmlElement("w:r")
        run.append(element)
        paragraph._p.append(run)

    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    run_with(begin)
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = f" {instruction} "
    run_with(instr)
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    run_with(separate)
    paragraph.add_run(cached)
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run_with(end)


def _bookmark(paragraph: Paragraph, name: str, number: int) -> None:
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(number))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(number))
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


def _refresh_fields_on_open(b: DocBuilder) -> None:
    settings = b.doc.settings.element
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    settings.append(update)


def _cell_text(
    cell: _Cell, text: str, *, size: float, bold: bool = False, color: RGBColor | None = None
) -> Paragraph:
    p: Paragraph = cell.paragraphs[0]
    run = p.add_run(text)
    run.bold, run.font.size = bold, Pt(size)
    if color is not None:
        run.font.color.rgb = color
    return p


def _no_borders(table: Table) -> None:
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "nil")
        borders.append(border)
    table._tbl.tblPr.append(borders)


def _cover(b: DocBuilder, data: MemoirExportData) -> None:
    """A banner of the brand colour, the market, the buyer in a light box, the company and
    its coordinates at the bottom: what the buyer sees first."""
    doc = b.doc
    white = RGBColor(0xFF, 0xFF, 0xFF)
    banner = doc.add_table(rows=1, cols=1)
    _no_borders(banner)
    cell = banner.rows[0].cells[0]
    _shade(cell, str(b.brand))
    p = _cell_text(cell, "MÉMOIRE TECHNIQUE", size=26, bold=True, color=white)
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(28), Pt(4)
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p = cell.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p.paragraph_format.space_after = Pt(28)
    run = p.add_run("Réponse à la consultation")
    run.font.size, run.font.color.rgb = Pt(12), RGBColor.from_string(tint(b.brand, 0.25))

    for _ in range(2):
        doc.add_paragraph()
    if data.logo:
        p = doc.add_paragraph()
        p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        p.add_run().add_picture(io.BytesIO(data.logo), height=Cm(3))
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(18), Pt(18)
    run = p.add_run(data.tender_title)
    run.bold, run.font.size, run.font.color.rgb = True, Pt(18), b.brand

    facts = [
        (label, value)
        for label, value in (
            ("Acheteur", data.buyer),
            ("Référence", data.reference),
            ("Lot", data.lot),
            ("Version", f"{data.version} — {french_date(data.exported_at.date())}"),
        )
        if value
    ]
    box = doc.add_table(rows=len(facts), cols=2)
    _no_borders(box)
    box.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, (label, value) in enumerate(facts):
        left, right = box.rows[i].cells
        for c in (left, right):
            _shade(c, tint(b.brand, 0.08))
        _cell_text(left, label, size=10.5, bold=True, color=GREY)
        _cell_text(right, value, size=11.5, bold=True)
    set_widths(box, (3.2, 11.3))

    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = p.add_run("Présenté par")
    run.font.size, run.font.color.rgb = Pt(10), GREY
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(data.company)
    run.bold, run.font.size, run.font.color.rgb = True, Pt(16), b.brand
    for line in [*data.company_lines, data.signatory]:
        if line:
            p = doc.add_paragraph()
            p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(line)
            run.font.size, run.font.color.rgb = Pt(10), GREY
    b.page_break()


def _toc(b: DocBuilder, titles: list[str]) -> None:
    p = b.doc.add_paragraph(style="Title")
    p.add_run("Sommaire").font.size = Pt(20)
    _paragraph_borders(p._p.get_or_add_pPr(), {"bottom": (12, 4, str(b.brand))})
    p.paragraph_format.space_after = Pt(18)
    width = Cm(21.0 - 2 * 2.2)  # A4 minus the margins set by DocBuilder
    for i, title in enumerate(titles):
        entry = b.doc.add_paragraph()
        entry.paragraph_format.space_after = Pt(8)
        entry.paragraph_format.tab_stops.add_tab_stop(
            width, WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS
        )
        run = entry.add_run(f"{title}\t")
        run.font.size = Pt(max(11.5, b.min_size))
        _complex_field(entry, f"PAGEREF _Toc{i + 1} \\h", "1")
    b.page_break()


def build_memoir(data: MemoirExportData) -> DocBuilder:
    b = DocBuilder(
        brand_color=data.brand_color,
        logo=data.logo,
        company=data.company,
        font=data.font,
        font_size=data.font_size,
    )
    b.doc.core_properties.title = f"Mémoire technique — {data.tender_title}"[:250]
    b.doc.styles["Normal"].paragraph_format.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
    _cover(b, data)
    titles = [c.title for c in data.chapters]
    if data.requirements:
        titles.append("Correspondance avec les exigences du CCTP")
    _toc(b, titles)
    for i, chapter in enumerate(data.chapters, start=1):
        if i > 1:
            b.page_break()  # each chapter starts on a new page
        start = len(b.doc.paragraphs)
        if chapter.markdown:
            b.markdown(chapter.markdown, heading_offset=-1)
        else:
            b.heading(chapter.title, 1)
            b.paragraph("[À COMPLÉTER : chapitre non rédigé]")
        _bookmark(b.doc.paragraphs[start], f"_Toc{i}", i)
    if data.requirements:
        b.page_break()
        start = len(b.doc.paragraphs)
        b.heading("Correspondance avec les exigences du CCTP", 1)
        _bookmark(b.doc.paragraphs[start], f"_Toc{len(titles)}", len(titles))
        b.table(
            ["Exigence", "Contenu", "Traitée dans le chapitre"],
            [[r.ref, r.text, r.chapter or "—"] for r in data.requirements],
            widths_cm=(2.4, 9.2, 5),
        )
    b.header_footer(
        f"{data.company} — {data.tender_title}"[:150],
        f"Mémoire technique — {data.company}"
        + (f" — Réf. {data.reference}" if data.reference else ""),
        first_page_plain=True,
    )
    _refresh_fields_on_open(b)
    return b
