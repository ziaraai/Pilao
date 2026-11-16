"""Chiffrage (ADR-049): reading the grid, checking the AI's lines, broken links, prices."""

import io
from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.domain.price_grid import PriceFileError, grid_text, read_workbook
from app.domain.pricing import (
    LineIn,
    PriceLine,
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


def test_twin_of_a_broken_link_is_folded_into_its_line() -> None:
    """Real model on the 26020M DQE: the yearly table listed B32 (BPU, no quantity) and H32
    (DQE, the fixed 0, with the quantity) as two lines. One line, H32 its broken link."""
    sheets = read_workbook(rillieux_like())
    twins = [
        *proposed(),
        line("H32", "Gymnase A", section="prestation annuelle", quantity_cell="I32"),
    ]
    twins[2] = line(
        "B32", "Gymnase A", section="prestation annuelle"
    )  # no quantity on the BPU side
    lines, warnings = validate_lines(twins, sheets)
    assert [ln.id for ln in lines] == ["DQE!B5", "DQE!B6", "DQE!B32", "DQE!B42"]
    assert lines[2].quantity == Decimal(2) and warnings == []
    assert broken_links(lines, sheets) == {"DQE!B32": ["H32"]}


def test_a_line_given_on_the_copy_side_is_moved_to_the_origin() -> None:
    sheets = read_workbook(rillieux_like())
    only_copy = [p for p in proposed() if p.price_cell != "B32"]
    only_copy.append(line("H32", "Gymnase A", section="prestation annuelle", quantity_cell="I32"))
    lines, _ = validate_lines(only_copy, sheets)
    yearly = next(ln for ln in lines if ln.section == "prestation annuelle")
    assert yearly.id == "DQE!B32" and yearly.quantity == Decimal(2)  # the BPU price is filled too
    assert broken_links(lines, sheets) == {"DQE!B32": ["H32"]}


def test_label_read_from_its_cell() -> None:
    """The model gives the label's cell (short answers on a 300-line DPGF): the server reads
    the text itself; a label typed by the model is only a fallback."""
    sheets = read_workbook(rillieux_like())
    from_cell = line("B5", "", label_cell="A5", quantity_cell="I5")
    typed = line("B6", "Gymnase B (tapé)", label_cell="I6", quantity_cell="I6")  # I6 is a number
    lines, _ = validate_lines([from_cell, typed], sheets)
    assert [ln.label for ln in lines] == ["Gymnase A", "Gymnase B (tapé)"]


def dpgf_with_option() -> bytes:
    """The shape of a DPGF « nettoyage de livraison » (Abdraouf, Bat E): prices per m², an
    option at the bottom that the buyer wants priced but « pour mémoire »."""
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "DPGF"
    ws["B7"] = "Nettoyage en vue d'OPR"
    rows = (
        (8, "Du niveau SS-1 au niveau R+7 surface noble", 5221),
        (9, "Vitrages 2 faces", 780),
        (20, "OPTION : Shampouinage moquette", 264),
        (21, "Shampouinage des escaliers", 40),
    )
    for row, label, qty in rows:
        ws[f"B{row}"], ws[f"C{row}"], ws[f"D{row}"] = label, "m²", qty
        ws[f"F{row}"] = f"=D{row}*E{row}"
    ws["F23"] = "=SUM(F8:F9)"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def dpgf_lines() -> list[LineIn]:
    def m2(cell: str, row: int, **kw: object) -> LineIn:
        base: dict[str, object] = {"sheet": "DPGF", "section": "Nettoyage en vue d'OPR"}
        base.update(label_cell=f"B{row}", unit="m²", quantity_cell=f"D{row}", price_cell=cell)
        base.update(kw)
        return LineIn.model_validate(base)

    return [
        m2("E8", 8),
        m2("E9", 9),
        m2("E20", 20),  # « OPTION : … »: an option by its label, even unflagged
        m2("E21", 21, option=True),  # flagged by the reading
    ]


def test_options_priced_but_kept_out_of_the_total() -> None:
    """Bat E: 20 868,70 € HT for the base, the carpet shampoo « PM » beside it."""
    lines, _ = validate_lines(dpgf_lines(), read_workbook(dpgf_with_option()))
    assert [ln.option for ln in lines] == [False, False, True, True]
    entries = {
        "DPGF!E8": {"price_cents": 170},
        "DPGF!E9": {"price_cents": 96},
        "DPGF!E20": {"price_cents": 400},
        "DPGF!E21": {"price_cents": 500},
    }
    out = compute(lines, entries, RATES, rate_cents=None)
    assert out.total_cents == 5221 * 170 + 780 * 96  # 8 875,70 + 748,80
    assert out.options_cents == 264 * 400 + 40 * 500
    assert {p.id: p.total_cents for p in out.lines}["DPGF!E20"] == 264 * 400  # still shown
    writes = fill_writes(lines, out, {})
    assert writes["DPGF"]["E20"] == 4.0  # the buyer asked for its price: written


def test_an_unpriced_option_is_still_missing() -> None:
    lines, _ = validate_lines(dpgf_lines(), read_workbook(dpgf_with_option()))
    out = compute(lines, {"DPGF!E8": {"price_cents": 170}}, RATES, rate_cents=None)
    assert out.missing_count == 3 and out.options_cents == 0


@pytest.mark.parametrize(
    ("section", "label", "expected"),
    [
        ("Nettoyage", "OPTION : Shampouinage moquette", True),
        ("Nettoyage", "Option 2 - lavage des façades", True),
        ("PSE n°1 : vitrerie haute", "Vitrages", True),
        ("Prestations supplémentaires éventuelles", "Vitrages", True),
        ("Variante", "Produits écolabellisés", True),
        ("Nettoyage", "Optionnel selon planning", False),
        ("Nettoyage", "Vitrages, en option si demandé", False),
        ("Prestations", "Locaux techniques", False),
    ],
)
def test_option_known_by_its_words(section: str, label: str, expected: bool) -> None:
    sheets = read_workbook(dpgf_with_option())
    proposal = LineIn(sheet="DPGF", section=section, label=label, price_cell="E8")
    lines, _ = validate_lines([proposal], sheets)
    assert lines[0].option is expected


def test_option_kept_when_stored_and_read_back() -> None:
    lines, _ = validate_lines(dpgf_lines(), read_workbook(dpgf_with_option()))
    again = [PriceLine.from_dict(ln.to_dict()) for ln in lines]
    assert again == lines
    old = lines[0].to_dict()
    del old["option"]  # a line stored before options existed
    assert PriceLine.from_dict(old).option is False


def test_option_hours_stay_out_of_the_memoir() -> None:
    lines, _ = validate_lines(dpgf_lines(), read_workbook(dpgf_with_option()))
    entries = {"DPGF!E8": {"hours": "0.05"}, "DPGF!E20": {"hours": "0.2"}}
    summary = hours_summary(lines, compute(lines, entries, RATES, rate_cents=None))
    assert summary is not None
    assert [r["libelle"] for r in summary["lignes"]] == [
        "Du niveau SS-1 au niveau R+7 surface noble"
    ]
