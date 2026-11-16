"""The memoir written into the buyer's own frame (ADR-051).

The buyer's Word file is opened as it is (python-docx keeps its styles, headers, footers and
pictures), the candidate's name is written where the frame asks for it, and each chapter is
inserted right under the box it answers, without repeating its title. A chapter that answers
no box is added at the end with its title. The answers take the font the RC imposes; the
buyer's own text is never touched.
"""

import io
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from docx import Document
from docx.document import Document as DocxDocument
from docx.enum.text import WD_COLOR_INDEX, WD_PARAGRAPH_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.shared import Cm, Pt
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from app.domain import markdown as md
from app.domain.frame import _fold, match_chapters
from app.exports.docx_builder import todo
from app.exports.memoir_docx import MemoirExportData

_DOTS = re.compile(r"[.…_]{3,}")
_NAME_LABEL = re.compile(r"candidat|raison sociale|denomination|soumissionnaire")
_ANCHOR_MAX = 300  # longer paragraphs are instructions, not titles


@dataclass
class FrameResult:
    content: bytes
    warnings: list[str] = field(default_factory=list)
    to_complete: list[str] = field(default_factory=list)


def _text(element: BaseOxmlElement) -> str:
    return "".join(t.text or "" for t in element.iter(qn("w:t"))).strip()


def _first_cell_text(table: BaseOxmlElement) -> str:
    cell = next(table.iter(qn("w:tc")), None)
    return _text(cell) if cell is not None else ""


def _fill_name(doc: DocxDocument, company: str) -> bool:
    """« Nom du candidat : ……… » → « Nom du candidat : ENG PRO » (first such field only)."""
    paragraphs = list(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                paragraphs.extend(cell.paragraphs)
    for p in paragraphs:
        if not _NAME_LABEL.search(_fold(p.text)) or not _DOTS.search(p.text):
            continue
        written = False
        for run in p.runs:
            if _DOTS.search(run.text):
                run.text = _DOTS.sub("" if written else company, run.text, count=1)
                run.text = _DOTS.sub("", run.text)
                written = True
        return written
    return False


class _Writer:
    """Markdown → paragraphs and tables appended to the frame, in its own styles."""

    def __init__(self, doc: DocxDocument, font: str | None, size: float | None) -> None:
        self.doc, self.font, self.size = doc, font, size
        self.todos: list[str] = []

    def _style(self, run: Run) -> None:
        if self.font:
            run.font.name = self.font
            r_pr = run._element.get_or_add_rPr()
            fonts = r_pr.get_or_add_rFonts()
            for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
                fonts.set(qn(attr), self.font)
        if self.size:
            run.font.size = Pt(self.size)

    def runs(self, p: Paragraph, runs: Sequence[md.Run], bold: bool = False) -> Paragraph:
        for r in runs:
            if r.kind == "todo":
                self.todos.append(r.text)
                run = p.add_run(todo(r.text))
                run.bold = True
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            else:
                run = p.add_run(r.text)
                run.bold = True if (bold or r.kind == "strong") else None
                if r.kind == "em":
                    run.italic = True
            self._style(run)
        return p

    def paragraph(self) -> Paragraph:
        p: Paragraph = self.doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        return p

    def heading(self, runs: Sequence[md.Run], size_up: float) -> None:
        p = self.paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.keep_with_next = True
        self.runs(p, runs, bold=True)
        for run in p.runs:
            run.font.size = Pt((self.size or 11) + size_up)

    def table(
        self, head: Sequence[Sequence[md.Run]], rows: Sequence[Sequence[Sequence[md.Run]]]
    ) -> None:
        columns = max([len(head), *(len(r) for r in rows)])
        table = self.doc.add_table(rows=1 + len(rows), cols=columns)
        try:
            table.style = "Table Grid"
        except KeyError:  # a frame without Word's grid style: thin lines drawn directly
            _grid(table._tbl)
        for j in range(columns):
            cell = table.rows[0].cells[j]
            _shade(cell._tc, "D9D9D9")
            self.runs(cell.paragraphs[0], head[j] if j < len(head) else [], bold=True)
        for i, row in enumerate(rows, start=1):
            for j in range(columns):
                p = table.rows[i].cells[j].paragraphs[0]
                p.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
                self.runs(p, row[j] if j < len(row) else [])
        self.paragraph()

    def chapter(self, source: str, with_title: str | None) -> None:
        """``with_title``: written as a title (a chapter added at the end); otherwise the
        chapter's own first title is left out, the box above already holds it."""
        if with_title:
            self.heading(md.inline(with_title), 2)
        skipped = False
        for block in md.parse(source):
            if isinstance(block, md.Heading):
                if not skipped and block.level <= 2:
                    skipped = True  # the chapter's title
                    continue
                self.heading(block.runs, 1 if block.level <= 3 else 0)
            elif isinstance(block, md.ListBlock):
                for n, item in enumerate(block.items, start=1):
                    p = self.paragraph()
                    p.paragraph_format.left_indent = Cm(0.6)
                    p.paragraph_format.first_line_indent = Cm(-0.4)
                    marker = f"{n}. " if block.ordered else "• "
                    self.runs(p, [md.Run("text", marker), *item])
            elif isinstance(block, md.Table):
                self.table(block.head, block.rows)
            else:
                self.runs(self.paragraph(), block.runs)


def _shade(tc: BaseOxmlElement, fill: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)
    tc.get_or_add_tcPr().append(shading)


def _grid(tbl: BaseOxmlElement) -> None:
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        border = OxmlElement(f"w:{side}")
        border.set(qn("w:val"), "single")
        border.set(qn("w:sz"), "4")
        border.set(qn("w:color"), "808080")
        borders.append(border)
    tbl.tblPr.append(borders)


def fill_frame(frame: bytes, data: MemoirExportData) -> FrameResult:
    doc = Document(io.BytesIO(frame))
    body = doc.element.body
    result = FrameResult(b"")
    if not _fill_name(doc, data.company):
        result.warnings.append("Le nom du candidat n'a pas été trouvé dans le cadre : écrivez-le.")

    anchors: list[BaseOxmlElement] = []
    texts: list[str] = []
    boxes: list[int] = []
    for child in body.iterchildren():
        if child.tag == qn("w:tbl"):
            boxes.append(len(anchors))
            anchors.append(child)
            texts.append(_first_cell_text(child))
        elif child.tag == qn("w:p"):
            text = _text(child)
            if text and len(text) <= _ANCHOR_MAX and not _DOTS.search(text):
                anchors.append(child)
                texts.append(text)
    titles = [c.title for c in data.chapters]
    matches = match_chapters(titles, texts, boxes)

    writer = _Writer(doc, data.font, data.font_size)
    end: list[str] = []
    for chapter, match in zip(data.chapters, matches, strict=True):
        source = chapter.markdown or f"## {chapter.title}\n\n{todo('chapitre non rédigé')}"
        if match.anchor is None:
            end.append(chapter.title)
            continue
        before = set(body.iterchildren())
        writer.chapter(source, None)
        added = [c for c in body.iterchildren() if c not in before and c.tag != qn("w:sectPr")]
        cursor = anchors[match.anchor]
        for element in added:
            cursor.addnext(element)
            cursor = element
        if match.uncertain:
            result.warnings.append(
                f"« {chapter.title} » a été placé sous l'encadré « {texts[match.anchor][:80]} » "
                "d'après l'ordre du cadre ou le sens des mots : vérifiez que c'est le bon."
            )
    for title in end:
        chapter = next(c for c in data.chapters if c.title == title)
        writer.chapter(chapter.markdown or f"## {title}\n\n{todo('chapitre non rédigé')}", title)
        result.warnings.append(
            f"« {title} » ne correspond à aucun encadré du cadre : ajouté à la fin, à déplacer "
            "ou à retirer."
        )
    out = io.BytesIO()
    doc.save(out)
    result.content = out.getvalue()
    result.to_complete = list(dict.fromkeys(writer.todos))
    return result
