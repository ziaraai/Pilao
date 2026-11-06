"""Word → PDF with LibreOffice headless (US-4.6 CA2), in the worker only.

Each conversion gets its own LibreOffice profile directory: two conversions sharing one
would block each other (LibreOffice locks its profile), and none is left behind.
"""

import logging
import shutil
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.documents.convert import ConversionUnavailable, soffice_convert

logger = logging.getLogger("pilao.pdf")


class PdfUnavailable(Exception):
    """The conversion cannot be done here: retrying will not help."""


class PdfConverter(Protocol):
    def convert(self, docx: bytes) -> bytes: ...


class LibreOfficeConverter:
    def __init__(self, soffice: str, timeout: int) -> None:
        self._soffice, self._timeout = soffice, timeout

    def convert(self, docx: bytes) -> bytes:
        if not self._soffice or shutil.which(self._soffice) is None:
            raise PdfUnavailable("LibreOffice n'est pas installé sur le serveur.")
        try:
            return soffice_convert(docx, "docx", "pdf", self._timeout)
        except ConversionUnavailable as exc:
            message = str(exc).replace("La conversion", "La conversion PDF")
            raise PdfUnavailable(message) from exc


@lru_cache
def get_pdf_converter() -> PdfConverter:
    s = get_settings()
    return LibreOfficeConverter(s.soffice_path, s.pdf_timeout_seconds)
