"""What is missing in a dossier (« Ce qu'il manque », ADR-048): pure rules.

A missing item is a ``[À COMPLÉTER : …]`` marker. Two spellings of the same item share a key
(``marker_key``) and make one line of the list. Each item belongs to a drawer of the profile
(``classify``, a keyword fallback when the model did not say). Answering replaces the marker;
completing rewrites only the unit that holds it — the sentence, the list line or the table
cell — spliced back by the server, so the rest of the chapter cannot change; removing deletes
that unit.
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.domain.memoir_checks import TO_COMPLETE, marker_key

__all__ = [
    "COMPANY_KINDS",
    "KINDS",
    "Marker",
    "MissingKind",
    "Unit",
    "answer",
    "classify",
    "marker_key",
    "markers",
    "remove",
    "splice",
    "units",
]

MissingKind = Literal["staff", "equipment", "certification", "reference", "identity", "tender"]
KINDS: tuple[MissingKind, ...] = (
    "staff",
    "equipment",
    "certification",
    "reference",
    "identity",
    "tender",
)
COMPANY_KINDS: tuple[MissingKind, ...] = KINDS[:5]

# Checked in this order: « effectif total » is the company's identity, not a team; an
# « équipement » is equipment before it is an « équipe ».
_RULES: tuple[tuple[MissingKind, tuple[str, ...]], ...] = (
    (
        "identity",
        (
            "siret",
            "siren",
            "adresse du siege",
            "siege social",
            "representant",
            "chiffre d affaires",
            "effectif total",
            "forme juridique",
            "tva",
            "kbis",
            "capital social",
        ),
    ),
    (
        "certification",
        ("certification", "certificat", "certifie", "iso", "label", "qualipropre", "qualibat"),
    ),
    ("reference", ("reference", "chantier similaire", "chantiers similaires", "client")),
    (
        "equipment",
        (
            "equipement",
            "materiel",
            "machine",
            "autolaveuse",
            "monobrosse",
            "aspirateur",
            "vehicule",
            "nacelle",
            "produit",
        ),
    ),
    (
        "staff",
        (
            "agent",
            "personnel",
            "effectif",
            "encadrant",
            "encadrement",
            "chef d equipe",
            "salarie",
            "intervenant",
            "equipe",
        ),
    ),
)


def _word(word: str) -> re.Pattern[str]:
    # the start of a word (« agents » is an « agent »); a short word must be whole (« iso »
    # is not « isolation »)
    end = r"(?!\w)" if len(word) <= 3 else ""
    return re.compile(rf"(?<!\w){re.escape(word)}{end}")


_PATTERNS = [(kind, [_word(w) for w in words]) for kind, words in _RULES]


def classify(text: str) -> MissingKind:
    """The drawer of a missing item from its words; ``tender`` (answered in place) otherwise."""
    key = marker_key(text)
    for kind, patterns in _PATTERNS:
        if any(p.search(key) for p in patterns):
            return kind
    return "tender"


@dataclass(frozen=True)
class Marker:
    key: str
    text: str
    start: int
    end: int


def markers(markdown: str) -> list[Marker]:
    return [
        Marker(marker_key(m.group(1)), m.group(1).strip(), m.start(), m.end())
        for m in TO_COMPLETE.finditer(markdown)
    ]


@dataclass(frozen=True)
class Unit:
    start: int
    end: int
    text: str
    shape: Literal["sentence", "line", "cell", "heading"]


_HEADING = re.compile(r"\s*#{1,6}\s+")
_BULLET = re.compile(r"\s*(?:[-*+]|\d+[.)])\s+")
_ENDS = ".!?…"
_ABBREVIATIONS = {"M", "Mme", "Mlle", "Mmes", "n°", "N°", "cf", "etc", "p", "art", "env", "St"}
_LAST_WORD = re.compile(r"(\w+°?)$")


def _line_bounds(markdown: str, start: int, end: int) -> tuple[int, int]:
    line_start = markdown.rfind("\n", 0, start) + 1
    line_end = markdown.find("\n", end)
    return line_start, len(markdown) if line_end < 0 else line_end


def _is_end(markdown: str, i: int, line_start: int, line_end: int) -> bool:
    """``markdown[i]`` closes a sentence: a final sign followed by a blank or the line's end,
    not the dot of an abbreviation (« M. Dupont »)."""
    if markdown[i] not in _ENDS:
        return False
    if i + 1 < line_end and not markdown[i + 1].isspace():
        return False
    if markdown[i] == ".":
        word = _LAST_WORD.search(markdown[line_start:i])
        if word and word.group(1) in _ABBREVIATIONS:
            return False
    return True


def _strip_span(markdown: str, start: int, end: int) -> tuple[int, int]:
    while start < end and markdown[start].isspace():
        start += 1
    while end > start and markdown[end - 1].isspace():
        end -= 1
    return start, end


def _unit_of(markdown: str, marker: Marker) -> Unit:
    line_start, line_end = _line_bounds(markdown, marker.start, marker.end)
    line = markdown[line_start:line_end]
    if heading := _HEADING.match(line):
        s, e = _strip_span(markdown, line_start + heading.end(), line_end)
        return Unit(s, e, markdown[s:e], "heading")
    if line.lstrip().startswith("|"):
        left = markdown.rfind("|", line_start, marker.start)
        right = markdown.find("|", marker.end, line_end)
        s, e = _strip_span(markdown, left + 1, line_end if right < 0 else right)
        return Unit(s, e, markdown[s:e], "cell")
    if bullet := _BULLET.match(line):
        s, e = _strip_span(markdown, line_start + bullet.end(), line_end)
        return Unit(s, e, markdown[s:e], "line")
    start = line_start
    for i in range(marker.start - 1, line_start - 1, -1):
        if _is_end(markdown, i, line_start, line_end):
            start = i + 1
            break
    end = line_end
    for i in range(marker.end, line_end):
        if _is_end(markdown, i, line_start, line_end):
            end = i + 1
            break
    s, e = _strip_span(markdown, start, end)
    return Unit(s, e, markdown[s:e], "sentence")


def units(markdown: str, key: str) -> list[Unit]:
    """The distinct units holding a marker of ``key``, in the order of the text."""
    found: dict[tuple[int, int], Unit] = {}
    for m in markers(markdown):
        if m.key == key:
            unit = _unit_of(markdown, m)
            found.setdefault((unit.start, unit.end), unit)
    return sorted(found.values(), key=lambda u: u.start)


def splice(markdown: str, unit: Unit, new_text: str) -> str:
    return markdown[: unit.start] + new_text + markdown[unit.end :]


def answer(markdown: str, key: str, value: str) -> str:
    """Every marker of ``key`` replaced by ``value``, word for word; the others untouched."""
    out = markdown
    for m in reversed(markers(markdown)):
        if m.key == key:
            out = out[: m.start] + value + out[m.end :]
    return out


def remove(markdown: str, key: str) -> str:
    """The units holding a marker of ``key`` deleted: a sentence, a list item (its whole line),
    a table cell (emptied, the row kept); in a title only the marker goes. A paragraph left
    empty disappears, without leaving more than one blank line between two blocks."""
    out = markdown
    for unit in reversed(units(markdown, key)):
        line_start, line_end = _line_bounds(out, unit.start, unit.end)
        if unit.shape == "heading":
            cleaned = " ".join(
                TO_COMPLETE.sub(
                    lambda m: "" if marker_key(m.group(1)) == key else m.group(0), unit.text
                ).split()
            )
            out = out[: unit.start] + cleaned + out[unit.end :]
            line_start, line_end = _line_bounds(out, unit.start, unit.start + len(cleaned))
            out = out[:line_start] + out[line_start:line_end].rstrip() + out[line_end:]
        elif unit.shape == "cell":
            out = out[: unit.start] + out[unit.end :]
        elif unit.shape == "line":
            out = out[:line_start] + out[min(line_end + 1, len(out)) :]
        else:
            start, end = unit.start, unit.end
            if out[end:line_end].strip():
                while end < line_end and out[end] in " \t":
                    end += 1
            else:
                while start > line_start and out[start - 1] in " \t":
                    start -= 1
            out = out[:start] + out[end:]
            line_start, line_end = _line_bounds(out, start, start)
            if not out[line_start:line_end].strip():
                out = out[:line_start] + out[min(line_end + 1, len(out)) :]
    return re.sub(r"\n{3,}", "\n\n", out)
