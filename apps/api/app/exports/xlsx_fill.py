"""Write numbers into the buyer's own spreadsheet, cell by cell, in its XML (ADR-049).

The price file goes back to the buyer: everything but the written cells must stay as it was
(formatting, drawings, print area, formulas). openpyxl rewrites the whole workbook and drops
the drawings, so the sheet XML is edited directly: the written cells get a number, every
formula loses its cached result and the workbook asks for a full calculation on opening, so
Excel and LibreOffice show the right totals.
"""

import io
import posixpath
import re
import zipfile

from lxml import etree

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL = re.compile(r"^([A-Z]{1,3})([1-9][0-9]{0,6})$")
# CT_Workbook children that come after calcPr (calcPr must be placed before them)
_AFTER_CALC = (
    "oleSize",
    "customWorkbookViews",
    "pivotCaches",
    "smartTagPr",
    "smartTagTypes",
    "webPublishing",
    "fileRecoveryPr",
    "webPublishObjects",
    "extLst",
)


class XlsxFillError(Exception):
    """The file or a cell cannot be written (not a workbook, unknown sheet, formula cell)."""


def _q(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def split_cell(ref: str) -> tuple[int, int]:
    """« B5 » → (column 2, row 5); raises ``XlsxFillError`` on anything else."""
    match = _CELL.match(ref)
    if not match:
        raise XlsxFillError(f"Case invalide : {ref}")
    col = 0
    for ch in match.group(1):
        col = col * 26 + ord(ch) - 64
    return col, int(match.group(2))


def _number(value: float) -> str:
    text = repr(float(value))
    return text.removesuffix(".0")


def _sheet_paths(z: zipfile.ZipFile) -> dict[str, str]:
    workbook = etree.fromstring(z.read("xl/workbook.xml"))
    rels = etree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets = {
        r.get("Id"): r.get("Target") or "" for r in rels.iter(f"{{{PKG_REL_NS}}}Relationship")
    }
    paths: dict[str, str] = {}
    for sheet in workbook.iter(_q("sheet")):
        target = targets.get(sheet.get(f"{{{REL_NS}}}id"), "")
        path = target.lstrip("/") if target.startswith("/") else posixpath.join("xl", target)
        paths[sheet.get("name") or ""] = posixpath.normpath(path)
    return paths


def _row(sheet_data: etree._Element, number: int) -> etree._Element:
    for row in sheet_data.iter(_q("row")):
        current = int(row.get("r") or 0)
        if current == number:
            return row
        if current > number:
            new = etree.Element(_q("row"), r=str(number))
            row.addprevious(new)
            return new
    return etree.SubElement(sheet_data, _q("row"), r=str(number))


def _cell(row: etree._Element, ref: str, col: int) -> etree._Element:
    for cell in row.iter(_q("c")):
        current = split_cell(cell.get("r") or "")[0]
        if current == col:
            return cell
        if current > col:
            new = etree.Element(_q("c"), r=ref)
            cell.addprevious(new)
            return new
    return etree.SubElement(row, _q("c"), r=ref)


def _write_sheet(xml: bytes, writes: dict[str, float]) -> etree._Element:
    root = etree.fromstring(xml)
    sheet_data = root.find(_q("sheetData"))
    if sheet_data is None:
        sheet_data = etree.SubElement(root, _q("sheetData"))
    for ref, value in writes.items():
        col, number = split_cell(ref)
        cell = _cell(_row(sheet_data, number), ref, col)
        if cell.find(_q("f")) is not None:
            raise XlsxFillError(f"La case {ref} contient une formule.")
        for child in list(cell):
            cell.remove(child)
        cell.attrib.pop("t", None)
        etree.SubElement(cell, _q("v")).text = _number(value)
    return root


def _drop_cached_results(root: etree._Element) -> None:
    for cell in root.iter(_q("c")):
        if cell.find(_q("f")) is not None:
            for cached in cell.findall(_q("v")):
                cell.remove(cached)
            cell.attrib.pop("t", None)


def _ask_full_calculation(xml: bytes) -> bytes:
    root = etree.fromstring(xml)
    calc = root.find(_q("calcPr"))
    if calc is None:
        calc = etree.Element(_q("calcPr"))
        later = next((c for c in root if etree.QName(c).localname in _AFTER_CALC), None)
        if later is not None:
            later.addprevious(calc)
        else:
            root.append(calc)
    calc.set("fullCalcOnLoad", "1")
    return bytes(etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True))


def fill_xlsx(data: bytes, writes: dict[str, dict[str, float]]) -> bytes:
    """``writes``: sheet name → {cell: number}. Returns the new file's bytes."""
    try:
        source = zipfile.ZipFile(io.BytesIO(data))
        paths = _sheet_paths(source)
    except (zipfile.BadZipFile, KeyError, etree.XMLSyntaxError) as exc:
        raise XlsxFillError("Ce fichier n'est pas un classeur Excel lisible.") from exc
    unknown = [name for name in writes if name not in paths]
    if unknown:
        raise XlsxFillError(f"Feuille introuvable : {unknown[0]}")
    by_path = {paths[name]: cells for name, cells in writes.items()}
    sheet_paths = set(paths.values())
    out = io.BytesIO()
    with source, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            content = source.read(item.filename)
            try:
                if item.filename in sheet_paths:
                    root = _write_sheet(content, by_path.get(item.filename, {}))
                    _drop_cached_results(root)
                    content = etree.tostring(
                        root, xml_declaration=True, encoding="UTF-8", standalone=True
                    )
                elif item.filename == "xl/workbook.xml":
                    content = _ask_full_calculation(content)
            except etree.XMLSyntaxError as exc:
                raise XlsxFillError("Ce fichier n'est pas un classeur Excel lisible.") from exc
            target.writestr(item, content)
    return out.getvalue()
