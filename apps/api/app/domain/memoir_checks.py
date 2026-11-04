"""Deterministic guards on generated chapters (docs/08 §4, CLAUDE.md §5.1).

The model must not invent company data. Whatever it writes, the text goes through:
* the chapter title forced to the planned (possibly imposed) title;
* `[À COMPLÉTER : …]` markers collected;
* commitments detected ("nous garantissons", "sous 2 heures"…) for the user to validate;
* every number checked against the data the model was given: a number that appears in none
  of the inputs is flagged — that is where invented facts usually hide.
"""

import re
import unicodedata
from dataclasses import dataclass

TO_COMPLETE = re.compile(r"\[\s*À\s+COMPLÉTER\s*:\s*([^\]]+)\]", re.IGNORECASE)
_COMMITMENT_PATTERNS = (
    r"nous (nous )?engageons",
    r"nous garantissons",
    r"garanti[es]? ",
    r"sans d[ée]lai",
    r"sous \d+\s*(h|heures?|min|minutes?|jours?)",
    r"dans un d[ée]lai de \d+",
    r"24\s*h\s*/\s*24",
    r"7\s*j\s*/\s*7",
    r"z[ée]ro (d[ée]faut|r[ée]clamation)",
    r"100\s*%",
)
# A number may be glued to its unit ("8h", "15min", "3m²"); references like CCTP-12 are not
# numbers (preceded by a dash), nor are digits inside words.
_NUMBER = re.compile(r"(?<![\w.,-])(\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?!\d)|\d+(?:[.,]\d+)?)(?!\d)")
_IGNORED_NUMBERS = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}  # list markers, ordinals...


@dataclass(frozen=True)
class Flag:
    type: str  # to_complete | commitment | number | length
    text: str


def _norm_number(raw: str) -> str:
    return (
        re.sub(r"[ \u00a0\u202f]", "", raw).replace(",", ".").rstrip("0").rstrip(".")
        if "." in raw or "," in raw
        else re.sub(r"[ \u00a0\u202f]", "", raw)
    )


def numbers_in(text: str) -> set[str]:
    return {_norm_number(m.group(1)) for m in _NUMBER.finditer(text)}


def force_title(markdown: str, title: str) -> str:
    """The chapter starts with exactly ``## <planned title>`` (an imposed title is kept)."""
    body = markdown.strip()
    lines = body.split("\n")
    if lines and lines[0].lstrip().startswith("#"):
        lines = lines[1:]
    return f"## {title}\n\n" + "\n".join(lines).strip()


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def count_words(markdown: str) -> int:
    return len(re.findall(r"\w+", TO_COMPLETE.sub("", markdown)))


def check_chapter(
    markdown: str, context: str, model_commitments: list[str], word_budget: int
) -> list[Flag]:
    flags: list[Flag] = [
        Flag("to_complete", m.group(1).strip()) for m in TO_COMPLETE.finditer(markdown)
    ]

    found: list[str] = []
    for sentence in _sentences(markdown):
        plain = unicodedata.normalize("NFC", sentence.lower())
        if any(re.search(p, plain) for p in _COMMITMENT_PATTERNS):
            found.append(sentence.lstrip("-*• ").strip())
    for c in model_commitments:
        if c.strip() and c.strip() not in found:
            found.append(c.strip())
    flags += [Flag("commitment", c[:300]) for c in dict.fromkeys(found)]

    known = numbers_in(context)
    text_without_markers = TO_COMPLETE.sub("", markdown)
    for sentence in _sentences(text_without_markers):
        unknown = sorted(n for n in numbers_in(sentence) - known if n not in _IGNORED_NUMBERS)
        if unknown:
            flags.append(
                Flag("number", f"{', '.join(unknown)} — absent de vos données : {sentence[:200]}")
            )

    words = count_words(markdown)
    if word_budget and words > word_budget * 1.3:
        flags.append(
            Flag("length", f"{words} mots pour un budget de {word_budget} : à raccourcir.")
        )
    return flags
