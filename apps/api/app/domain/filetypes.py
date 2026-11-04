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

ALLOWED = (PDF, DOCX, XLSX, ZIP, PNG, JPEG)


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
        try:
            with zipfile.ZipFile(fileobj) as zf:  # lists entries only, extracts nothing
                names = set(zf.namelist())
        except (zipfile.BadZipFile, ValueError, OSError):
            return None
        finally:
            fileobj.seek(0)
        if "word/document.xml" in names:
            return DOCX
        if "xl/workbook.xml" in names:
            return XLSX
        return ZIP
    return None
