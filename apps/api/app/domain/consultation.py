"""A consultation read from its documents (25/11): who asks for the quote, where the works
are, how to reach the client, which document holds the quantities to price.

The model proposes each fact with the file and page it read it on; the server keeps only the
facts that page really has (an e-mail as written, a phone number digit for digit, a name or an
address by most of its words). A fact missing from the documents stays empty: nothing is
guessed.
"""

import re
import unicodedata
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator

FACTS = (
    "title",
    "client_name",
    "client_address",
    "site_address",
    "contact_name",
    "contact_email",
    "contact_phone",
    "reference",
)
# the dossier's column of each fact
COLUMNS = {
    "title": "title",
    "client_name": "buyer_name",
    "client_address": "client_address",
    "site_address": "site_address",
    "contact_name": "contact_name",
    "contact_email": "contact_email",
    "contact_phone": "contact_phone",
    "reference": "reference",
}
MAX_LENGTH = {"title": 300, "client_name": 300, "contact_name": 300, "reference": 300}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9]{2,}")


class FactIn(BaseModel):
    value: str = Field(max_length=500)
    file: str = Field(max_length=500)
    page: int = Field(ge=1, le=10_000)


class PriceFileIn(BaseModel):
    file: str = Field(max_length=500)
    reason: str = Field(default="", max_length=300)


class ConsultationReadOut(BaseModel):
    """The answer of the prompt ``lecture_consultation``."""

    facts: dict[str, FactIn] = Field(default_factory=dict)
    price_files: list[PriceFileIn] = Field(default_factory=list, max_length=10)

    @field_validator("facts", mode="before")
    @classmethod
    def _known_only(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: v for k, v in value.items() if k in FACTS and v}
        return value


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,;")


def _on_page(name: str, value: str, page: str) -> str | None:
    """The value as kept when the page has it, else None."""
    if name == "contact_email":
        email = value.strip().lower()
        return email if _EMAIL.match(email) and email in page.lower() else None
    if name == "contact_phone":
        digits = _digits(value)
        if len(digits) < 9 or digits not in _digits(page):
            return None
        return (
            " ".join(digits[i : i + 2] for i in range(0, len(digits), 2))
            if len(digits) == 10
            else value.strip()
        )
    words = set(_WORD.findall(_fold(value)))
    if not words:
        return None
    on_page = set(_WORD.findall(_fold(page)))
    if len(words & on_page) < max(1, round(0.7 * len(words))):
        return None
    return _clean(value)[: MAX_LENGTH.get(name, 1000)]


def check_facts(
    read: ConsultationReadOut, pages: dict[tuple[str, int], str]
) -> dict[str, tuple[str, str, int]]:
    """{fact: (value, file, page)} for each fact the cited page really has."""
    kept: dict[str, tuple[str, str, int]] = {}
    for name, item in read.facts.items():
        text = pages.get((item.file, item.page))
        if text is None:
            continue
        value = _on_page(name, item.value, text)
        if value:
            kept[name] = (value, item.file, item.page)
    return kept


def placeholder_title(today: date) -> str:
    """The title of a consultation created from its documents, until they are read."""
    return f"Consultation du {today:%d/%m/%Y}"
