"""OCR of scanned pages (Tesseract, French) behind a small interface."""

from functools import lru_cache
from typing import Protocol

from PIL.Image import Image


class OcrUnavailable(Exception):
    """No OCR engine on this machine: pages are kept without text, and the user is told."""


class OcrEngine(Protocol):
    def image_to_text(self, image: Image) -> str: ...


class TesseractOcr:
    def __init__(self, lang: str = "fra", timeout_seconds: int = 60) -> None:
        self._lang, self._timeout = lang, timeout_seconds

    def image_to_text(self, image: Image) -> str:
        import pytesseract

        try:
            text: str = pytesseract.image_to_string(
                image, lang=self._lang, timeout=self._timeout, config="--psm 3"
            )
        except pytesseract.TesseractNotFoundError as exc:
            raise OcrUnavailable("Tesseract n'est pas installé") from exc
        except RuntimeError as exc:  # pytesseract raises RuntimeError on timeout
            raise OcrUnavailable(f"OCR interrompu : {exc}") from exc
        return text


@lru_cache
def get_ocr_engine() -> OcrEngine:
    return TesseractOcr()
