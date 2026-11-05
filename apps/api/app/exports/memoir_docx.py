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

from docx.enum.text import WD_PARAGRAPH_ALIGNMENT, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.shared import Cm, Pt
from docx.text.paragraph import Paragraph

from app.exports.dc_forms import french_date
from app.exports.docx_builder import GREY, DocBuilder


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


def _cover(b: DocBuilder, data: MemoirExportData) -> None:
    doc = b.doc
    for _ in range(3):
        doc.add_paragraph()
    if data.logo:
        p = doc.add_paragraph()
        p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        p.add_run().add_picture(io.BytesIO(data.logo), height=Cm(3))
    p = doc.add_paragraph(style="Title")
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    p.add_run("Mémoire technique")
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = p.add_run(data.tender_title)
    run.bold, run.font.size = True, Pt(15)
    for line in (
        f"Acheteur : {data.buyer}" if data.buyer else None,
        f"Référence : {data.reference}" if data.reference else None,
        f"Lot : {data.lot}" if data.lot else None,
    ):
        if line:
            p = doc.add_paragraph()
            p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            p.add_run(line).font.size = Pt(12)
    for _ in range(4):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = p.add_run(data.company)
    run.bold, run.font.size, run.font.color.rgb = True, Pt(14), b.brand
    p = doc.add_paragraph()
    p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
    run = p.add_run(f"Version {data.version} — {french_date(data.exported_at.date())}")
    run.font.size, run.font.color.rgb = Pt(10), GREY
    b.page_break()


def _toc(b: DocBuilder, titles: list[str]) -> None:
    p = b.doc.add_paragraph(style="Title")
    p.add_run("Sommaire").font.size = Pt(18)
    width = Cm(21.0 - 2 * 2.2)  # A4 minus the margins set by DocBuilder
    for i, title in enumerate(titles):
        entry = b.doc.add_paragraph()
        entry.paragraph_format.tab_stops.add_tab_stop(
            width, WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS
        )
        entry.add_run(f"{title}\t")
        _complex_field(entry, f"PAGEREF _Toc{i + 1} \\h", "1")
    b.page_break()


def build_memoir(data: MemoirExportData) -> DocBuilder:
    b = DocBuilder(brand_color=data.brand_color, logo=data.logo, company=data.company)
    b.doc.core_properties.title = f"Mémoire technique — {data.tender_title}"[:250]
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
        f"Mémoire technique — {data.company}",
        first_page_plain=True,
    )
    _refresh_fields_on_open(b)
    return b
