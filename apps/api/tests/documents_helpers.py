"""Build small PDF / DOCX files for tests."""

import io

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def make_pdf(pages: list[list[str]]) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    for lines in pages:
        y = 800
        for line in lines:
            pdf.drawString(50, y, line)
            y -= 16
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def make_blank_pdf(page_count: int = 3) -> bytes:
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    for _ in range(page_count):
        pdf.rect(50, 50, 200, 200)  # drawing only: no text layer, like a scan
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def make_docx(items: list[tuple[str, str]], table: list[list[str]] | None = None) -> bytes:
    doc = Document()
    for style, text in items:
        if style.startswith("Heading"):
            doc.add_heading(text, level=int(style.split()[-1]))
        else:
            doc.add_paragraph(text)
    if table:
        t = doc.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                t.cell(r, c).text = value
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
