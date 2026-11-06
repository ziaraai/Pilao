"""Detect the real type of an uploaded file from its content (never trust the client)."""

import zipfile
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class DetectedType:
    mime: str
    extension: str


PDF = DetectedType("application/pdf", "pdf")
DOCX = DetectedType(
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"
)
XLSX = DetectedType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx")
ZIP = DetectedType("application/zip", "zip")
PNG = DetectedType("image/png", "png")
JPEG = DetectedType("image/jpeg", "jpg")
# LibreOffice and older Office files (ADR-034): read after a conversion by LibreOffice
ODT = DetectedType("application/vnd.oasis.opendocument.text", "odt")
ODS = DetectedType("application/vnd.oasis.opendocument.spreadsheet", "ods")
DOC = DetectedType("application/msword", "doc")
XLS = DetectedType("application/vnd.ms-excel", "xls")

ALLOWED = (PDF, DOCX, XLSX, ZIP, PNG, JPEG, ODT, ODS, DOC, XLS)
TEXT_TO_CONVERT = (ODT, DOC)  # word processing: to PDF (a DCE keeps its pages) or DOCX
SHEETS_TO_CONVERT = (ODS, XLS)  # spreadsheets: to XLSX
_OPENDOCUMENT = {ODT.mime: ODT, ODS.mime: ODS}
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # Office 97-2003 compound file


def label(types: tuple[DetectedType, ...] | list[DetectedType]) -> str:
    """« PDF, DOCX, DOC… » for refusal messages."""
    return ", ".join(t.extension.upper() for t in types)


def detect(fileobj: BinaryIO) -> DetectedType | None:
    """Return the type if it is one we accept, else None. Leaves the cursor at 0."""
    fileobj.seek(0)
    head = fileobj.read(8)
    fileobj.seek(0)
    if head.startswith(b"%PDF-"):
        return PDF
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"PK"):
        opendocument = None
        try:
            with zipfile.ZipFile(fileobj) as zf:  # lists entries only, extracts nothing
                names = set(zf.namelist())
                if "mimetype" in names and zf.getinfo("mimetype").file_size < 100:
                    opendocument = zf.read("mimetype").decode("ascii", "replace").strip()
        except (zipfile.BadZipFile, ValueError, OSError):
            return None
        finally:
            fileobj.seek(0)
        if "word/document.xml" in names:
            return DOCX
        if "xl/workbook.xml" in names:
            return XLSX
        if opendocument in _OPENDOCUMENT and "content.xml" in names:
            return _OPENDOCUMENT[opendocument]
        return ZIP
    if head == _OLE_MAGIC:
        return _ole(fileobj)
    return None


def _ole(fileobj: BinaryIO) -> DetectedType | None:
    """Word 97-2003 or Excel 97-2003, from the streams of the compound file."""
    import olefile

    try:
        with olefile.OleFileIO(fileobj) as ole:
            if ole.exists("WordDocument"):
                return DOC
            if ole.exists("Workbook") or ole.exists("Book"):
                return XLS
    except (OSError, ValueError):  # a damaged or truncated compound file
        return None
    finally:
        fileobj.seek(0)
    return None
