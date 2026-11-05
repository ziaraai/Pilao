"""Word documents in the company's colours (US-4.5, US-4.6 CA1).

One builder for every generated document: A4, Arial (rendered by LibreOffice with its
metric-compatible Liberation Sans), headings in the brand colour, the logo in the header,
"Page X / Y" in the footer, and every ``[À COMPLÉTER : …]`` highlighted in yellow and
collected, so the document knows what the company still has to fill in.
"""

import io
import re
from collections.abc import Sequence

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_BREAK, WD_COLOR_INDEX, WD_PARAGRAPH_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.table import _Cell
from docx.text.paragraph import Paragraph

from app.domain import markdown as md

DEFAULT_BRAND = "011844"  # Pilao navy, when the company has not chosen a colour
FONT = "Arial"
GREY = RGBColor(0x64, 0x74, 0x8B)
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def todo(what: str) -> str:
    return f"[À COMPLÉTER : {what}]"


def _brand(color: str | None) -> RGBColor:
    m = _HEX.match(color or "")
    return RGBColor.from_string((m.group(1) if m else DEFAULT_BRAND).upper())


def _set_font(style_font: object, size: float | None = None) -> None:
    font = style_font  # docx.text.font.Font
    font.name = FONT  # type: ignore[attr-defined]
    if size:
        font.size = Pt(size)  # type: ignore[attr-defined]
    r_pr = font._element.get_or_add_rPr()  # type: ignore[attr-defined]
    fonts = r_pr.get_or_add_rFonts()
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(attr), FONT)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        fonts.attrib.pop(qn(attr), None)  # a theme font would win over ours


def _field(paragraph: Paragraph, instruction: str, placeholder: str = "1") -> None:
    """A Word field (PAGE, NUMPAGES…) that Word and LibreOffice compute when laying out."""
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), instruction)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = placeholder
    run.append(text)
    field.append(run)
    paragraph._p.append(field)


def _shade(cell: _Cell, hex_color: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), hex_color)
    tc_pr.append(shading)


class DocBuilder:
    def __init__(self, *, brand_color: str | None, logo: bytes | None, company: str) -> None:
        self.doc = Document()
        self.brand = _brand(brand_color)
        self.logo = logo
        self.company = company
        self.todos: list[str] = []
        section = self.doc.sections[0]
        section.page_height, section.page_width = Cm(29.7), Cm(21.0)
        for side in ("left_margin", "right_margin"):
            setattr(section, side, Cm(2.2))
        section.top_margin, section.bottom_margin = Cm(2.0), Cm(2.0)
        self._styles()
        self.doc.core_properties.author = company
        self.doc.core_properties.comments = "Brouillon pré-rempli par Pilao, à relire."

    def _styles(self) -> None:
        styles = self.doc.styles
        normal = styles["Normal"]
        _set_font(normal.font, 10.5)
        normal.paragraph_format.space_after = Pt(6)
        normal.paragraph_format.line_spacing = 1.15
        for name, size in (
            ("Title", 22),
            ("Heading 1", 15),
            ("Heading 2", 12.5),
            ("Heading 3", 11),
        ):
            style = styles[name]
            _set_font(style.font, size)
            style.font.bold = True
            style.font.color.rgb = self.brand
            style.paragraph_format.space_before = Pt(12 if name != "Title" else 0)
            style.paragraph_format.space_after = Pt(6)
            style.paragraph_format.keep_with_next = True

    # ---------- text ------------------------------------------------------------------

    def runs(self, paragraph: Paragraph, text: str, bold: bool = False) -> Paragraph:
        """Plain text with its ``[À COMPLÉTER : …]`` markers highlighted (and collected)."""
        return self.md_runs(paragraph, md.inline(text), bold=bold)

    def md_runs(
        self, paragraph: Paragraph, runs: Sequence[md.Run], bold: bool = False
    ) -> Paragraph:
        for r in runs:
            if r.kind == "todo":
                self.todos.append(r.text)
                run = paragraph.add_run(todo(r.text))
                run.bold = True
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            else:
                run = paragraph.add_run(r.text)
                if bold or r.kind == "strong":  # otherwise inherit (a heading is bold)
                    run.bold = True
                if r.kind == "em":
                    run.italic = True
        return paragraph

    def title(self, text: str, subtitle: str | None = None) -> None:
        self.doc.add_paragraph(text, style="Title")
        if subtitle:
            p = self.doc.add_paragraph()
            run = p.add_run(subtitle)
            run.font.size, run.font.color.rgb = Pt(12), GREY

    def heading(self, text: str, level: int = 1) -> None:
        self.runs(self.doc.add_paragraph(style=f"Heading {min(max(level, 1), 3)}"), text)

    def paragraph(self, text: str = "", *, bold: bool = False) -> Paragraph:
        return self.runs(self.doc.add_paragraph(), text, bold=bold)

    def note(self, text: str) -> None:
        """Small grey italic text: how to use the document, where a value comes from."""
        p = self.doc.add_paragraph()
        run = p.add_run(text)
        run.italic, run.font.size, run.font.color.rgb = True, Pt(9), GREY

    def field(self, label: str, value: str | None, missing: str, source: str | None = None) -> None:
        """``Label : value`` — or ``Label : [À COMPLÉTER : missing]``; never a guess."""
        p = self.doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        p.add_run(f"{label} : ").bold = True
        self.runs(p, value if value else todo(missing))
        if value and source:
            run = p.add_run(f"  (source : {source})")
            run.font.size, run.font.color.rgb = Pt(8.5), GREY

    def checkboxes(self, *options: str) -> None:
        self.paragraph("     ".join(f"☐ {o}" for o in options))

    def bullets(self, items: Sequence[str]) -> None:
        for item in items:
            self.runs(self.doc.add_paragraph(style="List Bullet"), item)

    def table(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[str]],
        widths_cm: Sequence[float] | None = None,
    ) -> None:
        self.md_table(
            [md.inline(h) for h in headers], [[md.inline(c) for c in r] for r in rows], widths_cm
        )

    def md_table(
        self,
        head: Sequence[Sequence[md.Run]],
        rows: Sequence[Sequence[Sequence[md.Run]]],
        widths_cm: Sequence[float] | None = None,
    ) -> None:
        columns = max([len(head), *(len(r) for r in rows)])
        table = self.doc.add_table(rows=1 + len(rows), cols=columns)
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for j in range(columns):
            cell = table.rows[0].cells[j]
            _shade(cell, str(self.brand))
            p = cell.paragraphs[0]
            for r in head[j] if j < len(head) else []:
                run = p.add_run(todo(r.text) if r.kind == "todo" else r.text)
                run.bold, run.font.color.rgb = True, RGBColor(0xFF, 0xFF, 0xFF)
        for i, row in enumerate(rows, start=1):
            for j in range(columns):
                self.md_runs(table.rows[i].cells[j].paragraphs[0], row[j] if j < len(row) else [])
        if widths_cm:
            table.autofit = False
            grid = table._tbl.tblGrid
            for j, width in enumerate(widths_cm[:columns]):
                grid.gridCol_lst[j].w = Cm(width)  # LibreOffice reads the grid
                for row_ in table.rows:
                    row_.cells[j].width = Cm(width)  # Word reads the cells
        self.doc.add_paragraph()

    def markdown(self, source: str, heading_offset: int = 0) -> None:
        """A chapter: ``## Title`` becomes Heading 1 with ``heading_offset=-1``."""
        for block in md.parse(source):
            if isinstance(block, md.Heading):
                level = min(max(block.level + heading_offset, 1), 3)
                self.md_runs(self.doc.add_paragraph(style=f"Heading {level}"), block.runs)
            elif isinstance(block, md.ListBlock):
                style = "List Number" if block.ordered else "List Bullet"
                for item in block.items:
                    self.md_runs(self.doc.add_paragraph(style=style), item)
            elif isinstance(block, md.Table):
                self.md_table(block.head, block.rows)
            else:
                self.md_runs(self.doc.add_paragraph(), block.runs)

    def page_break(self) -> None:
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def new_section(self) -> None:
        self.doc.add_section(WD_SECTION.NEW_PAGE)

    # ---------- page furniture --------------------------------------------------------

    def header_footer(
        self, header_text: str, footer_text: str, first_page_plain: bool = False
    ) -> None:
        for section in self.doc.sections:
            section.different_first_page_header_footer = first_page_plain
            header = section.header.paragraphs[0]
            header.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
            if self.logo:
                header.add_run().add_picture(io.BytesIO(self.logo), height=Cm(1.1))
                header.add_run("    ")
            run = header.add_run(header_text)
            run.font.size, run.font.color.rgb = Pt(8.5), GREY
            footer = section.footer.paragraphs[0]
            footer.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            run = footer.add_run(f"{footer_text} — Page ")
            run.font.size, run.font.color.rgb = Pt(8.5), GREY
            _field(footer, "PAGE")
            run = footer.add_run(" / ")
            run.font.size, run.font.color.rgb = Pt(8.5), GREY
            _field(footer, "NUMPAGES")

    def to_bytes(self) -> bytes:
        out = io.BytesIO()
        self.doc.save(out)
        return out.getvalue()

    @property
    def to_complete(self) -> list[str]:
        return list(dict.fromkeys(self.todos))
