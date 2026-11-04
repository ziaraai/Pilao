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


def make_scanned_pdf(lines: list[str], pages: int = 1) -> bytes:
    """A PDF whose pages are *images* of text (no text layer), like a scanner output."""
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.utils import ImageReader

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 34)
    except OSError:
        font = ImageFont.load_default(size=34)
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    for _ in range(pages):
        image = Image.new("L", (1240, 1754), 255)  # A4 at 150 dpi
        draw = ImageDraw.Draw(image)
        for i, line in enumerate(lines):
            draw.text((90, 120 + i * 60), line, fill=0, font=font)
        pdf.drawImage(ImageReader(image), 0, 0, width=A4[0], height=A4[1])
        pdf.showPage()
    pdf.save()
    return buf.getvalue()
