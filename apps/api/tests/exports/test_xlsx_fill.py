"""Filling the buyer's price file cell by cell, in its XML (ADR-049)."""

import io
import zipfile

import pytest
from openpyxl import Workbook, load_workbook

from app.exports.xlsx_fill import XlsxFillError, fill_xlsx

DRAWING = "xl/drawings/drawing9.xml"
DRAWING_BODY = b'<?xml version="1.0"?><xdr:wsDr xmlns:xdr="urn:test">logo</xdr:wsDr>'


def buyer_file() -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "DQE"
    ws["A1"] = "Bâtiments sportifs"
    ws["A5"], ws["B5"], ws["H5"], ws["I5"], ws["J5"] = "Gymnase A", 0, "=B5", 208, "=I5*H5"
    ws["A6"], ws["H6"], ws["I6"], ws["J6"] = "Gymnase B", "=B6", 42, "=I6*H6"  # B6 is empty
    ws["A7"], ws["B7"] = "Libellé", "texte"
    ws["J10"] = "=SUM(J5:J6)"
    ws["B5"].number_format = '#,##0.00 "€"'
    other = wb.create_sheet("Garde")
    other["A1"] = "=DQE!J10"
    buf = io.BytesIO()
    wb.save(buf)
    # a drawing openpyxl would not keep: it must come out byte for byte
    out = io.BytesIO()
    with zipfile.ZipFile(buf) as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        zout.writestr(DRAWING, DRAWING_BODY)
    return out.getvalue()


def test_values_written_and_formulas_kept() -> None:
    filled = fill_xlsx(buyer_file(), {"DQE": {"B5": 250.0, "B6": 120.5}})
    wb = load_workbook(io.BytesIO(filled))
    ws = wb["DQE"]
    assert ws["B5"].value == 250 and ws["B6"].value == 120.5
    assert ws["H5"].value == "=B5" and ws["J10"].value == "=SUM(J5:J6)"
    assert ws["B5"].number_format == '#,##0.00 "€"'  # the buyer's formatting is untouched
    assert ws["A5"].value == "Gymnase A"


def test_other_parts_untouched() -> None:
    original = buyer_file()
    filled = fill_xlsx(original, {"DQE": {"B5": 1.0}})
    with zipfile.ZipFile(io.BytesIO(filled)) as z:
        assert z.read(DRAWING) == DRAWING_BODY
        names = set(z.namelist())
    with zipfile.ZipFile(io.BytesIO(original)) as z:
        assert names == set(z.namelist())


def test_cached_results_dropped_and_recalculation_asked() -> None:
    filled = fill_xlsx(buyer_file(), {"DQE": {"B5": 10.0}})
    with zipfile.ZipFile(io.BytesIO(filled)) as z:
        workbook = z.read("xl/workbook.xml").decode()
        sheets = [z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/sheet")]
    assert 'fullCalcOnLoad="1"' in workbook
    for xml in sheets:  # every formula of every sheet is computed again on opening
        assert "<f>" in xml
        for chunk in xml.split("<f>")[1:]:
            assert not chunk.split("</c>")[0].count("<v>")


def test_text_cell_becomes_a_number() -> None:
    filled = fill_xlsx(buyer_file(), {"DQE": {"B7": 3.0}})
    assert load_workbook(io.BytesIO(filled))["DQE"]["B7"].value == 3


def test_new_cell_and_new_row_in_order() -> None:
    filled = fill_xlsx(buyer_file(), {"DQE": {"C5": 7.5, "K8": 2.0, "A2": 1.0}})
    ws = load_workbook(io.BytesIO(filled))["DQE"]
    assert ws["C5"].value == 7.5 and ws["K8"].value == 2 and ws["A2"].value == 1
    with zipfile.ZipFile(io.BytesIO(filled)) as z:
        xml = z.read("xl/worksheets/sheet1.xml").decode()
    assert xml.index('r="B5"') < xml.index('r="C5"') < xml.index('r="H5"')
    assert xml.index('<row r="2"') < xml.index('<row r="5"') < xml.index('<row r="8"')


def test_refuses_formula_cells_unknown_sheets_and_bad_files() -> None:
    with pytest.raises(XlsxFillError):
        fill_xlsx(buyer_file(), {"DQE": {"H5": 1.0}})
    with pytest.raises(XlsxFillError):
        fill_xlsx(buyer_file(), {"Inconnue": {"B5": 1.0}})
    with pytest.raises(XlsxFillError):
        fill_xlsx(b"pas un classeur", {"DQE": {"B5": 1.0}})
    with pytest.raises(XlsxFillError):
        fill_xlsx(buyer_file(), {"DQE": {"B0": 1.0}})
