"""The DPGF Pilao writes from a price file that is a document (25/11): the lines read, the
company's prices, the formulas, the VAT to choose."""

import io
from decimal import Decimal

from openpyxl import load_workbook

from app.domain.pricing import LinePrice, PriceLine, Priced
from app.exports.dpgf_xlsx import DpgfHeader, build_dpgf


def line(id: str, section: str, label: str, unit: str, qty: str | None, **kw: object) -> PriceLine:
    return PriceLine(
        id=id, sheet="", section=section, label=label, unit=unit,
        quantity=None if qty is None else Decimal(qty), price_cell="", hours_cell=None,
        rate_cell=None, hourly=False, surcharge="none", option=bool(kw.get("option")),
    )  # fmt: skip


def priced(id: str, cents: int | None, source: str = "price") -> LinePrice:
    return LinePrice(id=id, hours=None, rate_cents=None, price_cents=cents, total_cents=None,
                     source=source)  # type: ignore[arg-type]  # fmt: skip


HEADER = DpgfHeader(
    title="Traitement de sol", client="M. MAUDRY Gilles", site="8 rue des Écoles, 42120 Le Coteau",
    reference="DE36532", source="FICHE_INTERVENTION.pdf", company="ENG PRO",
)  # fmt: skip


def test_the_dpgf_holds_the_lines_the_prices_and_the_formulas() -> None:
    lines = [
        line("p1-001", "CUISINE", "Dégraissage du sol", "m²", "16.56"),
        line("p1-002", "WC", "Dégraissage du sol", "m²", "1.65"),
        line("p1-003", "", "Traitement des déchets", "u", "1"),
        line("p1-004", "AUTRES CORPS D'ÉTAT", "Plâtrerie", "m²", "10"),
        line("p1-005", "OPTIONS", "Shampouinage", "m²", "40", option=True),
    ]
    prices = Priced(
        lines=[priced("p1-001", 1250), priced("p1-002", None, "none"), priced("p1-003", 9000),
               priced("p1-004", None, "excluded"), priced("p1-005", 300)],
        total_cents=0, missing_count=1,
    )  # fmt: skip
    ws = load_workbook(io.BytesIO(build_dpgf(HEADER, lines, prices)))["DPGF"]
    rows: dict[str, int] = {}
    for r in range(1, ws.max_row + 1):
        if ws.cell(r, 2).value:
            rows.setdefault(str(ws.cell(r, 2).value), r)  # the first line of that label
    r = rows["Dégraissage du sol"]
    assert (ws.cell(r, 3).value, ws.cell(r, 4).value, ws.cell(r, 5).value) == ("m²", 16.56, 12.5)
    assert ws.cell(r, 6).value == f'=IF(E{r}="","",D{r}*E{r})'
    assert "Plâtrerie" not in rows  # a rubrique set aside is not offered
    assert ws.cell(rows["Traitement des déchets"], 5).value == 90
    total = rows.get("TOTAL HT") or next(
        rr for rr in range(1, ws.max_row + 1) if ws.cell(rr, 5).value == "TOTAL HT"
    )
    formula = ws.cell(total, 6).value
    assert formula.startswith("=SUM(") and str(rows["Traitement des déchets"]) in formula
    assert ws.cell(total + 1, 6).value == 0.2  # the VAT rate, to choose
    assert ws.cell(total + 3, 6).value == f"=F{total}+F{total + 2}"
    # the option apart, out of the total
    opt = next(rr for rr in range(total, ws.max_row + 1) if ws.cell(rr, 2).value == "Shampouinage")
    assert ws.cell(opt, 5).value == 3 and str(opt) not in formula
    # the header: whose dossier, from which file
    texts = " ".join(str(c.value) for row in ws.iter_rows(max_row=9) for c in row if c.value)
    assert "M. MAUDRY Gilles" in texts and "DE36532" in texts and "FICHE_INTERVENTION.pdf" in texts
