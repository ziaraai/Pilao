"""LibreOffice conversions, in the worker (ADR-034, ADR-019).

* LibreOffice and older Office files are read after a conversion: a DCE piece in ODT/DOC
  becomes a PDF (its pages are kept, so every fact still cites « file + page »), a document
  of the knowledge base becomes a DOCX (its headings are kept), a spreadsheet in ODS/XLS
  becomes an XLSX. The deposited file itself is kept as it is.
* the memoir's Word → PDF export goes through the same runner.

Each conversion gets its own LibreOffice profile directory: two conversions sharing one
would block each other (LibreOffice locks its profile), and none is left behind. Macros are
never run: LibreOffice does not execute them when it only converts a document.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.core.config import get_settings
from app.domain.filetypes import DOCX, PDF, SHEETS_TO_CONVERT, TEXT_TO_CONVERT, XLSX, DetectedType

logger = logging.getLogger("pilao.convert")

# --convert-to arguments: the output format, and the filter that writes it
_FILTERS = {
    "pdf": "pdf",
    "docx": "docx:MS Word 2007 XML",
    "xlsx": "xlsx:Calc MS Excel 2007 XML",
}
_MAGIC = {"pdf": b"%PDF", "docx": b"PK", "xlsx": b"PK"}


class ConversionUnavailable(Exception):
    """The conversion cannot be done here (LibreOffice missing, too slow, failed)."""


def soffice_convert(data: bytes, extension: str, target: str, timeout: int | None = None) -> bytes:
    """``data`` (a ``.extension`` file) converted to ``target`` (pdf, docx or xlsx)."""
    s = get_settings()
    binary = shutil.which(s.soffice_path) if s.soffice_path else None
    if binary is None:
        raise ConversionUnavailable("LibreOffice n'est pas installé sur le serveur.")
    with tempfile.TemporaryDirectory(prefix="pilao-office-") as tmp:
        work = Path(tmp)
        source = work / f"document.{extension}"
        source.write_bytes(data)
        outdir = work / "out"
        command = [
            binary,
            "--headless",
            "--norestore",
            "--nolockcheck",
            f"-env:UserInstallation={(work / 'profile').as_uri()}",
            "--convert-to",
            _FILTERS[target],
            "--outdir",
            str(outdir),
            str(source),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=timeout or s.pdf_timeout_seconds,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            raise ConversionUnavailable("La conversion a pris trop de temps.") from exc
        except subprocess.CalledProcessError as exc:
            logger.error("soffice failed: %s", exc.stderr[-2000:])
            raise ConversionUnavailable("La conversion a échoué.") from exc
        result = outdir / f"document.{target}"
        if not result.exists() or not result.read_bytes().startswith(_MAGIC[target]):
            raise ConversionUnavailable("La conversion n'a produit aucun fichier lisible.")
        return result.read_bytes()


def readable_form(data: bytes, kind: DetectedType, text_target: str) -> tuple[bytes, DetectedType]:
    """A file Pilao reads directly: unchanged, or converted (``text_target``: pdf or docx)."""
    if kind in TEXT_TO_CONVERT:
        return soffice_convert(data, kind.extension, text_target), (
            PDF if text_target == "pdf" else DOCX
        )
    if kind in SHEETS_TO_CONVERT:
        return soffice_convert(data, kind.extension, "xlsx"), XLSX
    return data, kind
