"""The font the RC imposes on the memoir (« Police Times New Roman, taille 11 »).

Read from the memoir format constraints the analysis already extracted, so a dossier analysed
before this rule existed needs no new (paid) analysis. Pure functions: no database, no network.
"""

import re
from dataclasses import dataclass
from typing import Any

# Longest names first: « Arial Narrow » before « Arial ». Helvetica is not installed on Word
# computers: Arial is its metric twin.
_FONTS: tuple[tuple[str, str], ...] = (
    ("times new roman", "Times New Roman"),
    ("arial narrow", "Arial Narrow"),
    ("century gothic", "Century Gothic"),
    ("trebuchet ms", "Trebuchet MS"),
    ("trebuchet", "Trebuchet MS"),
    ("book antiqua", "Book Antiqua"),
    ("courier new", "Courier New"),
    ("helvetica", "Arial"),
    ("garamond", "Garamond"),
    ("marianne", "Marianne"),
    ("calibri", "Calibri"),
    ("cambria", "Cambria"),
    ("verdana", "Verdana"),
    ("georgia", "Georgia"),
    ("tahoma", "Tahoma"),
    ("arial", "Arial"),
    ("times", "Times New Roman"),
)
_SIZE = r"(\d{1,2}(?:[.,]5)?)"
_AFTER_WORD = re.compile(r"\b(?:taille|corps|police)\b[^0-9\n]{0,30}?" + _SIZE, re.IGNORECASE)
_WITH_UNIT = re.compile(_SIZE + r"\s*(?:pts?|points)\b", re.IGNORECASE)
_MIN_SIZE, _MAX_SIZE = 8.0, 16.0  # a body size; « taille 40 » is something else


@dataclass(frozen=True)
class ImposedFont:
    name: str | None  # as Word names it
    size: float | None  # points


def _name(text: str) -> str | None:
    found = [  # the first one written; at the same place, the longest name (listed first)
        (m.start(), rank, name)
        for rank, (key, name) in enumerate(_FONTS)
        if (m := re.search(rf"\b{key}\b", text, re.IGNORECASE))
    ]
    return min(found)[2] if found else None


def _size(text: str, name: str | None) -> float | None:
    patterns = [_AFTER_WORD, _WITH_UNIT]
    if name:  # « Arial 10 »
        key = next(
            k for k, n in _FONTS if n == name and re.search(rf"\b{k}\b", text, re.IGNORECASE)
        )
        patterns.insert(0, re.compile(rf"\b{key}\b\s*,?\s*{_SIZE}", re.IGNORECASE))
    for pattern in patterns:
        for m in pattern.finditer(text):
            size = float(m.group(1).replace(",", "."))
            if _MIN_SIZE <= size <= _MAX_SIZE:
                return size
    return None


def read(text: str | None) -> ImposedFont | None:
    if not text:
        return None
    name = _name(text)
    size = _size(text, name)
    return ImposedFont(name, size) if name or size else None


def from_analysis(data: dict[str, Any]) -> ImposedFont | None:
    constraints = (data.get("memoir_requirements") or {}).get("format_constraints")
    return read(constraints if isinstance(constraints, str) else None)
