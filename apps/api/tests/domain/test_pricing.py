"""Chiffrage (ADR-049): reading the grid, checking the AI's lines, broken links, prices."""

import io
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.domain.price_grid import PriceFileError, grid_text, read_workbook
from app.domain.pricing import (
    LineIn,
    Rates,
    broken_links,
    compute,
    fill_writes,
    hours_summary,
    validate_lines,
)


def rillieux_like() -> bytes:
    """The shape of the 26020M DQE: price per day with hours × rate, the DQE beside it."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "DQE"
    ws["A3"] = "prestation quotidienne"
    ws["B4"], ws["C4"], ws["D4"], ws["I4"] = "prix € HT/J", "nombre d'heures", "coût horaire", "Qté"
    for row, name, qty in ((5, "Gymnase A", 208), (6, "Gymnase B", 188)):
        ws[f"A{row}"], ws[f"B{row}"], ws[f"D{row}"] = name, 0, 0
        ws[f"H{row}"], ws[f"I{row}"], ws[f"J{row}"] = f"=B{row}", qty, f"=I{row}*H{row}"
    ws["A30"] = "prestation annuelle"
    ws["A32"], ws["B32"], ws["H32"], ws["I32"], ws["J32"] = "Gymnase A", 0, 0, 2, "=I32*H32"
    ws["A42"], ws["B42"], ws["H42"], ws["I42"] = "Nuit (21h-6h)", 0, "=B42", 2
    ws["J47"] = "=SUM(J5:J42)"
    hidden = wb.create_sheet("Calculs")
    hidden.sheet_state = "hidden"
    hidden["A1"] = "secret"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def line(cell: str, label: str, **kw: object) -> LineIn:
    base: dict[str, object] = {
        "sheet": "DQE",
        "section": "prestation quotidienne",
        "label": label,
        "unit": "jour",
        "quantity_cell": None,
        "price_cell": cell,
        "hours_cell": None,
        "rate_cell": None,
        "hourly": False,
        "surcharge": "none",
    }
    base.update(kw)
    return LineIn.model_validate(base)


def proposed() -> list[LineIn]:
    return [
        line("B5", "Gymnase A", quantity_cell="I5", hours_cell="C5", rate_cell="D5"),
        line("B6", "Gymnase B", quantity_cell="I6", hours_cell="C6", rate_cell="D6"),
        line("B32", "Gymnase A", section="prestation annuelle", quantity_cell="I32"),
        line(
            "B42",
            "Nuit (21h-6h)",
            section="interventions",
            unit="heure",
            quantity_cell="I42",
            hourly=True,
            surcharge="night",
        ),
    ]


def test_read_and_grid_text() -> None:
    sheets = read_workbook(rillieux_like())
    assert [s.name for s in sheets] == ["DQE", "Calculs"] and sheets[1].hidden
    text, cut = grid_text(sheets)
    assert not cut
    assert "Feuille « DQE »" in text and "Calculs" not in text and "secret" not in text
    assert "A5: « Gymnase A »" in text and "H5: =B5" in text and "I5: 208" in text
    short, cut = grid_text(sheets, max_cells=5)
    assert cut and short.count(": ") <= 5


def test_read_refuses_other_files() -> None:
    with pytest.raises(PriceFileError):
        read_workbook(b"%PDF-1.4")


def test_validate_keeps_good_lines_and_reads_quantities_itself() -> None:
    sheets = read_workbook(rillieux_like())
    lines, warnings = validate_lines(proposed(), sheets)
    assert [ln.id for ln in lines] == ["DQE!B5", "DQE!B6", "DQE!B32", "DQE!B42"]
    assert [ln.quantity for ln in lines] == [Decimal(208), Decimal(188), Decimal(2), Decimal(2)]
    assert lines[0].hours_cell == "C5" and lines[0].rate_cell == "D5"
    assert warnings == []


def test_validate_drops_bad_proposals() -> None:
    sheets = read_workbook(rillieux_like())
    bad = [
        line("H5", "formule"),  # a formula: never overwritten
        line("A5", "texte"),  # holds a label, not a price
        line("B5", "Gymnase A"),
        line("B5", "doublon"),
        line("B99", "   "),  # no label
        line("ZZZZ1", "case impossible"),
        line("B5", "autre feuille", sheet="Inconnue"),
        line("A1", "feuille cachée", sheet="Calculs"),
        line("B6", "Gymnase B", hours_cell="H6", rate_cell="B6", quantity_cell="A6"),
    ]
    lines, warnings = validate_lines(bad, sheets)
    assert [ln.id for ln in lines] == ["DQE!B5", "DQE!B6"]
    assert lines[1].hours_cell is None and lines[1].rate_cell is None  # formula / the price
    assert lines[1].quantity is None  # « Gymnase B » is not a number
    assert len(warnings) == 1 and "7 lignes" in warnings[0]


def test_broken_link_found() -> None:
    sheets = read_workbook(rillieux_like())
    lines, _ = validate_lines(proposed(), sheets)
    mirrors = broken_links(lines, sheets)
    assert mirrors == {"DQE!B32": ["H32"]}  # H5, H6, H42 reprise the price; H32 is a 0


RATES = Rates(hourly_rate_cents=2500, night_pct=25, sunday_pct=None, holiday_pct=100)


def test_compute_hours_direct_price_and_hourly() -> None:
    sheets = read_workbook(rillieux_like())
    lines, _ = validate_lines(proposed(), sheets)
    entries = {
        "DQE!B5": {"hours": "2.5"},  # 2.5 h × 25 € = 62.50 € per day
        "DQE!B6": {"price_cents": 9000},  # a price typed directly
        "DQE!B32": {},  # nothing yet
    }
    out = compute(lines, entries, RATES, rate_cents=None)
    by_id = {c.id: c for c in out.lines}
    assert by_id["DQE!B5"].price_cents == 6250 and by_id["DQE!B5"].total_cents == 6250 * 208
    assert by_id["DQE!B6"].price_cents == 9000 and by_id["DQE!B6"].total_cents == 9000 * 188
    assert by_id["DQE!B32"].price_cents is None and by_id["DQE!B32"].missing
    assert by_id["DQE!B42"].price_cents == 3125  # 25 € + 25 % at night
    assert out.missing_count == 1
    assert out.total_cents == 6250 * 208 + 9000 * 188 + 3125 * 2


def test_compute_dossier_rate_and_missing_rates() -> None:
    sheets = read_workbook(rillieux_like())
    lines, _ = validate_lines(proposed(), sheets)
    out = compute(lines, {"DQE!B5": {"hours": "2"}}, Rates(None, None, None, None), rate_cents=3000)
    assert {c.id: c.price_cents for c in out.lines}["DQE!B5"] == 6000
    none = compute(lines, {"DQE!B5": {"hours": "2"}}, Rates(None, None, None, None), None)
    assert all(c.missing for c in none.lines)  # no rate at all: nothing can be priced
    night_only = Rates(hourly_rate_cents=2000, night_pct=None, sunday_pct=None, holiday_pct=None)
    nuit = {c.id: c for c in compute(lines, {}, night_only, None).lines}["DQE!B42"]
    assert nuit.missing  # a night price needs its surcharge: never guessed


def test_writes_and_hours_summary() -> None:
    sheets = read_workbook(rillieux_like())
    lines, _ = validate_lines(proposed(), sheets)
    entries = {"DQE!B5": {"hours": "2.5"}, "DQE!B32": {"price_cents": 40000}}
    out = compute(lines, entries, RATES, rate_cents=None)
    writes = fill_writes(lines, out, broken_links(lines, sheets))
    assert writes == {
        "DQE": {
            "B5": 62.5,
            "C5": 2.5,
            "D5": 25.0,
            "B32": 400.0,
            "H32": 400.0,  # the broken link gets the price too
            "B42": 31.25,
        }
    }
    summary = hours_summary(lines, out)
    assert summary == {
        "lignes": [
            {
                "rubrique": "prestation quotidienne",
                "libelle": "Gymnase A",
                "heures_par_unite": "2.5",
                "unite": "jour",
                "quantite": "208",
                "heures_annuelles": "520",
            }
        ],
        "heures_totales": "520",
    }
