"""Word → PDF with LibreOffice headless (US-4.6 CA2), in the worker only.

Each conversion gets its own LibreOffice profile directory: two conversions sharing one
would block each other (LibreOffice locks its profile), and none is left behind.
"""

import logging
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

logger = logging.getLogger("pilao.pdf")


class PdfUnavailable(Exception):
    """The conversion cannot be done here: retrying will not help."""


class PdfConverter(Protocol):
    def convert(self, docx: bytes) -> bytes: ...


class LibreOfficeConverter:
    def __init__(self, soffice: str, timeout: int) -> None:
        self._soffice, self._timeout = soffice, timeout

    def convert(self, docx: bytes) -> bytes:
        binary = shutil.which(self._soffice) if self._soffice else None
        if binary is None:
            raise PdfUnavailable("LibreOffice n'est pas installé sur le serveur.")
        with tempfile.TemporaryDirectory(prefix="pilao-pdf-") as tmp:
            work = Path(tmp)
            source = work / "memoire.docx"
            source.write_bytes(docx)
            command = [
                binary,
                "--headless",
                "--norestore",
                "--nolockcheck",
                f"-env:UserInstallation={(work / 'profile').as_uri()}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(work),
                str(source),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    timeout=self._timeout,
                    stdin=subprocess.DEVNULL,
                )
            except subprocess.TimeoutExpired as exc:
                raise PdfUnavailable("La conversion PDF a pris trop de temps.") from exc
            except subprocess.CalledProcessError as exc:
                logger.error("soffice failed: %s", exc.stderr[-2000:])
                raise PdfUnavailable("La conversion PDF a échoué.") from exc
            result = work / "memoire.pdf"
            if not result.exists() or not result.read_bytes().startswith(b"%PDF"):
                raise PdfUnavailable("La conversion PDF n'a produit aucun fichier.")
            return result.read_bytes()


@lru_cache
def get_pdf_converter() -> PdfConverter:
    s = get_settings()
    return LibreOfficeConverter(s.soffice_path, s.pdf_timeout_seconds)
