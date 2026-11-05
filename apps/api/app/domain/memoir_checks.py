"""Deterministic guards on generated chapters (docs/08 §4, CLAUDE.md §5.1).

The model must not invent company data. Whatever it writes, the text goes through:
* the chapter title forced to the planned (possibly imposed) title;
* `[À COMPLÉTER : …]` markers collected;
* commitments detected ("nous garantissons", "sous 2 heures"…) for the user to validate;
* every number and every proper noun checked against the data the model was given: one that
  appears in none of the inputs is flagged — that is where invented facts usually hide.

Each flag carries the ``term`` to highlight in the text (US-4.4 CA3).
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
_HEADING = re.compile(r"^\s*#{1,6}\s")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}")
_LIST_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_WORD = re.compile(r"[^\W\d_][\w'’-]*")
_ELISION = re.compile(r"^[a-zA-Z][’']")  # d'Ecolab, l'Oréal
# Capitalized by French administrative style, or generic sector acronyms: not names to check.
_GENERIC_WORDS = frozenset(
    [
        "acheteur",
        "titulaire",
        "marché",
        "marchés",
        "pouvoir",
        "adjudicateur",
        "maître",
        "maîtrise",
        "ouvrage",
        "œuvre",
        "état",
        "république",
        "client",
        "clients",
        "entreprise",
        "société",
        "direction",
        "responsable",
        "chef",
        "équipe",
        "agent",
        "agents",
        "prestataire",
        "annexe",
        "article",
        "chapitre",
        "lot",
        "lots",
        "mairie",
        "ville",
        "département",
        "région",
        "commune",
        "service",
        "services",
        "france",
        "français",
        "française",
        "europe",
        "européen",
        "européenne",
        "nous",
        "notre",
        "nos",
        "vous",
        "votre",
        "vos",
    ]
)
_GENERIC_ACRONYMS = frozenset(
    [
        "CCTP",
        "CCAP",
        "RC",
        "BPU",
        "DPGF",
        "DQE",
        "DCE",
        "AE",
        "PME",
        "TPE",
        "ETI",
        "HT",
        "TTC",
        "TVA",
        "EPI",
        "ISO",
        "QSE",
        "RSE",
        "CSE",
        "SST",
        "FDS",
        "CACES",
        "HACCP",
        "BTP",
        "VMC",
        "PMR",
        "ERP",
        "IGH",
        "SSIAP",
        "UV",
        "COV",
        "PSE",
        "DOE",
        "DUERP",
        "PPSPS",
        "PGC",
        "SIRET",
        "SIREN",
        "NAF",
        "URSSAF",
        "KBIS",
        "DC1",
        "DC2",
        "DUME",
    ]
)


@dataclass(frozen=True)
class Flag:
    type: str  # to_complete | commitment | number | name | length
    text: str
    term: str | None = None  # what to highlight in the chapter


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


def _segments(markdown: str) -> list[str]:
    """Sentences, list items and table cells: the places where a capital letter is expected.
    Titles are left out (they come from the plan)."""
    out: list[str] = []
    for raw in markdown.split("\n"):
        line = raw.strip()
        if not line or _HEADING.match(line) or _TABLE_RULE.match(line):
            continue
        cells = line.strip("|").split("|") if line.startswith("|") else [line]
        for cell in cells:
            cell = _LIST_MARKER.sub("", cell)
            out += [x.strip() for x in re.split(r"(?<=[.!?])\s+", cell) if x.strip()]
    return out


def count_words(markdown: str) -> int:
    return len(re.findall(r"\w+", TO_COMPLETE.sub("", markdown)))


def _known_words(context: str) -> set[str]:
    return {_ELISION.sub("", w).lower() for w in _WORD.findall(context)}


def _names(segment: str, known: set[str]) -> list[str]:
    """Capitalized words that do not start the segment, grouped ("Jean Dupont"), unknown."""
    groups: list[list[str]] = []
    previous_end = None
    for i, m in enumerate(_WORD.finditer(segment)):
        word = _ELISION.sub("", m.group())
        before = segment[: m.start()].rstrip()
        starts = i == 0 or before[-1:] in ":«(“\"'"
        capital = word[:1].isupper() and len(word) > 1 and not starts
        if not capital:
            previous_end = None
            continue
        if previous_end is not None and segment[previous_end : m.start()].isspace():
            groups[-1].append(word)
        else:
            groups.append([word])
        previous_end = m.end()
    names = []
    for group in groups:
        unknown = [
            w
            for w in group
            if w.lower() not in known
            and w.lower() not in _GENERIC_WORDS
            and w.upper() not in _GENERIC_ACRONYMS
        ]
        if unknown:
            names.append(" ".join(group))
    return names


def _commitments(markdown: str, model_commitments: list[str]) -> list[Flag]:
    found: dict[str, str | None] = {}
    for segment in _segments(markdown):
        plain = unicodedata.normalize("NFC", segment.lower())
        if any(re.search(p, plain) for p in _COMMITMENT_PATTERNS):
            found[segment] = segment
    for c in model_commitments:
        c = c.strip()
        if c and c not in found:
            found[c] = c if c in markdown else None
    return [Flag("commitment", c[:300], term) for c, term in found.items()]


def _to_complete(markdown: str) -> list[Flag]:
    return [Flag("to_complete", m.group(1).strip()) for m in TO_COMPLETE.finditer(markdown)]


def _length(markdown: str, word_budget: int) -> list[Flag]:
    words = count_words(markdown)
    if word_budget and words > word_budget * 1.3:
        return [Flag("length", f"{words} mots pour un budget de {word_budget} : à raccourcir.")]
    return []


def check_chapter(
    markdown: str, context: str, model_commitments: list[str], word_budget: int
) -> list[Flag]:
    flags = _to_complete(markdown) + _commitments(markdown, model_commitments)
    known_numbers, known_words = numbers_in(context), _known_words(context)
    seen: set[tuple[str, str]] = set()
    for segment in _segments(TO_COMPLETE.sub("", markdown)):
        for m in _NUMBER.finditer(segment):
            raw = m.group(1)
            number = _norm_number(raw)
            if number in known_numbers or number in _IGNORED_NUMBERS or ("n", raw) in seen:
                continue
            seen.add(("n", raw))
            flags.append(Flag("number", f"{raw} — absent de vos données : {segment[:200]}", raw))
        for name in _names(segment, known_words):
            if ("w", name) not in seen:
                seen.add(("w", name))
                flags.append(
                    Flag("name", f"{name} — absent de vos données : {segment[:200]}", name)
                )
    return flags + _length(markdown, word_budget)


def flags_after_edit(
    markdown: str, previous: list[dict[str, object]], word_budget: int
) -> list[Flag]:
    """The user's own words are not "invented": markers, commitments and length are recomputed;
    a number or a name the model had invented stays flagged while it is still in the text."""
    text = TO_COMPLETE.sub("", markdown)
    kept = [
        Flag(str(f["type"]), str(f["text"]), str(f["term"]))
        for f in previous
        if f.get("type") in ("number", "name") and f.get("term") and str(f["term"]) in text
    ]
    return (
        _to_complete(markdown) + _commitments(markdown, []) + kept + _length(markdown, word_budget)
    )
