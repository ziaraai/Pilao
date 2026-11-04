"""DCE vocabulary and file typing (US-3.1 CA2). See docs/02-glossaire-metier.md.

Typing is deterministic: first the file name, then (delivery 2) the first page's text. The
user can always correct it; a model is only considered later for the remaining doubts.
"""

import re
import unicodedata
from dataclasses import dataclass

KINDS = ("rc", "ccap", "cctp", "ae", "bpu", "dpgf", "dqe", "annex", "other")
KIND_LABELS = {
    "rc": "Règlement de la consultation (RC)",
    "ccap": "Cahier des clauses administratives particulières (CCAP)",
    "cctp": "Cahier des clauses techniques particulières (CCTP)",
    "ae": "Acte d'engagement (AE)",
    "bpu": "Bordereau des prix unitaires (BPU)",
    "dpgf": "Décomposition du prix global et forfaitaire (DPGF)",
    "dqe": "Détail quantitatif estimatif (DQE)",
    "annex": "Annexe",
    "other": "Autre",
}
BID_STATUSES = ("to_review", "in_progress", "submitted", "won", "lost", "dropped")

# (kind, patterns) in priority order; patterns run on a normalized, accent-free name.
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("rc", (r"\brc\b", r"reglement (de )?(la )?consultation")),
    ("ccap", (r"\bccap\b", r"clauses administratives particulieres")),
    ("cctp", (r"\bcctp\b", r"clauses techniques particulieres")),
    ("ae", (r"\bae\b", r"acte (d )?engagement", r"\battri ?1\b")),
    ("bpu", (r"\bbpu\b", r"bordereau (des )?prix")),
    ("dpgf", (r"\bdpgf\b", r"decomposition (du )?prix global")),
    ("dqe", (r"\bdqe\b", r"detail quantitatif")),
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


@dataclass(frozen=True)
class Typing:
    kind: str
    source: str  # "filename" | "content" | "none"


def kind_from_filename(path: str) -> Typing:
    name = normalize(path.rsplit("/", 1)[-1].rsplit(".", 1)[0])
    if name.startswith("annexe"):  # "Annexe 2 au CCTP - liste des locaux" is an annex
        return Typing("annex", "filename")
    for kind, patterns in _RULES:
        if any(re.search(p, name) for p in patterns):
            return Typing(kind, "filename")
    if re.search(r"\bannexe?s?\b|\bplans?\b|cadre (de )?(reponse|memoire)", name):
        return Typing("annex", "filename")
    return Typing("other", "none")


# Titles printed on the first page of each piece (normalized, accent-free).
_CONTENT_RULES: tuple[tuple[str, str], ...] = (
    ("rc", r"reglement (de )?(la )?consultation"),
    ("ccap", r"cahier des clauses administratives particulieres"),
    ("cctp", r"cahier des clauses techniques particulieres"),
    ("ae", r"acte (d )?engagement"),
    ("bpu", r"bordereau (des )?prix unitaires"),
    ("dpgf", r"decomposition (du )?prix global (et )?forfaitaire"),
    ("dqe", r"detail quantitatif (et )?estimatif"),
)


def kind_from_content(first_pages: str) -> Typing:
    """Typing from the beginning of the document, used when the name says nothing.

    Only the start is read: a CCTP often *mentions* the RC later on.
    """
    head = normalize(first_pages[:1500])
    best: tuple[int, str] | None = None
    for kind, pattern in _CONTENT_RULES:
        match = re.search(pattern, head)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), kind)
    return Typing(best[1], "content") if best else Typing("other", "none")
