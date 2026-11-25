"""A DPGF written by Pilao from a price file that is a document (25/11).

A contractor's « fiche d'intervention » in PDF cannot be filled in: its lines, read and checked
(``domain.pricing.validate_document_lines``), go into an Excel DPGF with the company's prices,
the amounts as formulas, sub-totals per rubric, the VAT rate to choose and the options apart.
A rubric set aside (another trade's) is not offered. Nothing is guessed: a line without price
keeps an empty yellow cell.
"""

import io
from dataclasses import dataclass

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

from app.domain.pricing import LinePrice, Priced, PriceLine

FONT = "Arial"
NAVY = "0B2A5B"
EUR = '#,##0.00 "€";-#,##0.00 "€";"-"'
QTY = "#,##0.00"
_thin = Side(style="thin", color="7F8C9D")
BOX = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
HEAD = PatternFill("solid", fgColor=NAVY)
SECTION = PatternFill("solid", fgColor="DCE6F2")
SUBTOTAL = PatternFill("solid", fgColor="F2F2F2")
INPUT = PatternFill("solid", fgColor="FFFF00")
TOTAL = PatternFill("solid", fgColor="C6D9F1")
WRAP = Alignment(wrap_text=True, vertical="center")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center")
COLUMNS = ("N°", "Désignation des ouvrages", "Unité", "Quantité", "Prix unitaire HT", "Montant HT")
VAT_COMMENT = (
    "À choisir : 20 % (taux normal), 10 % ou 5,5 % (travaux dans un logement de plus de 2 ans, "
    "avec l'attestation du client), ou 0 % en sous-traitance BTP (autoliquidation)."
)


@dataclass(frozen=True)
class DpgfHeader:
    title: str
    client: str | None
    site: str | None  # the address of the works
    reference: str | None  # the client's own reference (its quote number…)
    source: str  # the document the lines were read in
    company: str


class _Sheet:
    def __init__(self, ws: Worksheet) -> None:
        self.ws = ws
        self.row = 1

    def put(
        self,
        col: int,
        value: object,
        *,
        bold: bool = False,
        size: int = 10,
        color: str = "000000",
        fill: PatternFill | None = None,
        fmt: str | None = None,
        align: Alignment | None = None,
        border: bool = False,
        italic: bool = False,
    ) -> None:
        cell = self.ws.cell(self.row, col)
        cell.value = value  # type: ignore[assignment]  # str, number or formula
        cell.font = Font(name=FONT, bold=bold, size=size, color=color, italic=italic)
        if fill is not None:
            cell.fill = fill
        if fmt:
            cell.number_format = fmt
        if align is not None:
            cell.alignment = align
        if border:
            cell.border = BOX


def _price(p: LinePrice | None) -> float | None:
    return None if p is None or p.price_cents is None else p.price_cents / 100


def build_dpgf(header: DpgfHeader, lines: list[PriceLine], priced: Priced) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "DPGF"
    for letter, width in zip("ABCDEF", (8, 52, 9, 11, 15, 16), strict=True):
        ws.column_dimensions[letter].width = width
    s = _Sheet(ws)
    s.put(1, "DPGF — Décomposition du prix global et forfaitaire", bold=True, size=14, color=NAVY)
    s.row += 1
    s.put(1, header.title, bold=True, size=11)
    s.row += 2
    facts = [
        ("Entreprise", header.company),
        ("Client", header.client),
        ("Chantier", header.site),
        ("Référence", header.reference),
        ("Lu dans", header.source),
    ]
    for label, value in facts:
        if value:
            s.put(1, label, bold=True)
            s.put(2, value)
            s.row += 1
    s.row += 1
    for i, title in enumerate(COLUMNS, start=1):
        s.put(i, title, bold=True, color="FFFFFF", fill=HEAD, align=CENTER, border=True)
    ws.row_dimensions[s.row].height = 28
    head_row = s.row
    s.row += 1

    by_id = {p.id: p for p in priced.lines}
    offered = [ln for ln in lines if by_id.get(ln.id) is None or by_id[ln.id].source != "excluded"]
    base = [ln for ln in offered if not ln.option]
    options = [ln for ln in offered if ln.option]

    def priced_row(number: str, ln: PriceLine) -> int:
        r = s.row
        s.put(1, number, align=CENTER, border=True)
        s.put(2, ln.label, align=WRAP, border=True)
        s.put(3, ln.unit or None, align=CENTER, border=True)
        quantity = None if ln.quantity is None else float(ln.quantity)
        s.put(4, quantity, fmt=QTY, align=RIGHT, border=True, color="0000FF")
        price = _price(by_id.get(ln.id))
        s.put(5, price, fmt=EUR, border=True, fill=INPUT if price is None else None)
        s.put(6, f'=IF(E{r}="","",D{r}*E{r})', fmt=EUR, border=True)
        if len(ln.label) > 50:
            ws.row_dimensions[r].height = 13 * (len(ln.label) // 50 + 1)
        s.row += 1
        return r

    summed: list[int] = []  # sub-totals, and lines outside any rubric
    sections: list[tuple[str, list[PriceLine]]] = []
    for ln in base:
        if sections and sections[-1][0] == ln.section:
            sections[-1][1].append(ln)
        else:
            sections.append((ln.section, [ln]))
    n = 0
    for title, group in sections:
        if not title:
            for ln in group:
                n += 1
                summed.append(priced_row(str(n), ln))
            continue
        n += 1
        for col in range(1, 7):
            s.put(col, None, fill=SECTION, border=True)
        s.put(1, str(n), bold=True, fill=SECTION, align=CENTER, border=True)
        s.put(2, title, bold=True, fill=SECTION, align=WRAP, border=True)
        s.row += 1
        first = s.row
        for k, ln in enumerate(group, start=1):
            priced_row(f"{n}.{k}", ln)
        for col in range(1, 7):
            s.put(col, None, fill=SUBTOTAL, border=True)
        s.put(2, f"Sous-total {n} — {title}", bold=True, fill=SUBTOTAL, align=RIGHT, border=True)
        s.put(6, f"=SUM(F{first}:F{s.row - 1})", bold=True, fmt=EUR, fill=SUBTOTAL, border=True)
        summed.append(s.row)
        s.row += 1

    s.row += 1
    total = s.row
    s.put(5, "TOTAL HT", bold=True, align=RIGHT)
    refs = ",".join(f"F{r}" for r in summed) or "0"
    s.put(6, f"=SUM({refs})", bold=True, fmt=EUR, fill=TOTAL, border=True)
    s.row += 1
    s.put(5, "Taux de TVA", bold=True, align=RIGHT)
    s.put(6, 0.2, fmt="0.0%", fill=INPUT, border=True, color="0000FF")
    ws.cell(s.row, 6).comment = Comment(VAT_COMMENT, "Pilao")
    vat_rate = DataValidation(type="list", formula1='"0.2,0.1,0.055,0"', allow_blank=False)
    ws.add_data_validation(vat_rate)
    vat_rate.add(f"F{s.row}")
    s.row += 1
    s.put(5, "Montant TVA", bold=True, align=RIGHT)
    s.put(6, f"=F{total}*F{total + 1}", fmt=EUR, border=True)
    s.row += 1
    s.put(5, "TOTAL TTC", bold=True, align=RIGHT)
    s.put(6, f"=F{total}+F{total + 2}", bold=True, fmt=EUR, fill=TOTAL, border=True)
    s.row += 2

    if options:
        s.put(1, "Options (hors total)", bold=True, size=11, color=NAVY)
        s.row += 1
        first = s.row
        for k, ln in enumerate(options, start=1):
            priced_row(f"O{k}", ln)
        s.put(5, "Total des options HT", bold=True, align=RIGHT)
        s.put(6, f"=SUM(F{first}:F{s.row - 1})", bold=True, fmt=EUR, border=True)
        s.row += 2

    notes = (
        (
            "Cases jaunes : prix à saisir et taux de TVA. Montants, sous-totaux et totaux se "
            "calculent seuls."
        ),
        f"Quantités (en bleu) reprises de « {header.source} ».",
    )
    for note in notes:
        s.put(1, note, italic=True, size=9)
        s.row += 1

    ws.freeze_panes = f"A{head_row + 1}"
    ws.print_title_rows = f"{head_row}:{head_row}"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    if ws.sheet_properties.pageSetUpPr is not None:
        ws.sheet_properties.pageSetUpPr.fitToPage = True
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
