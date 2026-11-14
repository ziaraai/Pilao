"""Memoir outline (US-4.1): which plan, which requirements per chapter, how many words.

Rules (CLAUDE.md §5.4): the outline imposed by the RC wins, word for word and in order;
otherwise the company's template outline, ordered by the award criteria; otherwise the sector
default outline (docs/03-processus-metier.md). Everything here is deterministic.
"""

import re
from dataclasses import dataclass, field

from app.domain.dce import normalize

WORDS_PER_PAGE = 500
BODY_SIZE = 10.5  # points: the Word export's body text (app/exports/docx_builder.py)
DEFAULT_PAGES = 12  # when the RC sets no limit
MIN_SECTION_WORDS = 150

# Sector default (cleaning), from prompts/generation_memoire_chapitre.md.
SECTOR_DEFAULT_OUTLINE: tuple[str, ...] = (
    "Présentation de l'entreprise et compréhension du besoin",
    "Organisation et moyens humains affectés au marché",
    "Méthodologie d'intervention par type de local et fréquences",
    "Moyens matériels et produits",
    "Contrôle qualité et suivi de la prestation",
    "Hygiène, sécurité et formation du personnel",
    "Démarche environnementale et responsabilité sociale",
    "Planning de démarrage et de mise en place",
    "Références similaires",
)

# Requirement category -> words that identify the chapter that should answer it.
CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "staff": ("humain", "personnel", "effectif", "encadrement", "equipe", "organisation", "moyens"),
    "equipment": ("materiel", "equipement", "moyens techniques", "machine", "moyens"),
    "product": ("produit", "materiel", "consommable", "moyens"),
    "frequency": ("methodologie", "methode", "intervention", "frequence", "prestation"),
    "surface": ("methodologie", "methode", "intervention", "prestation", "local"),
    "schedule": ("planning", "horaire", "methodologie", "intervention", "organisation"),
    "quality": ("qualite", "controle", "suivi"),
    "reporting": ("suivi", "reporting", "controle", "qualite"),
    "safety": ("securite", "hygiene", "prevention", "formation"),
    "environment": ("environnement", "durable", "rse", "ecolog", "dechet"),
    "other": ("methodologie", "methode", "prestation", "comprehension"),
}

_STOPWORDS = {
    "de",
    "des",
    "du",
    "la",
    "le",
    "les",
    "et",
    "en",
    "au",
    "aux",
    "a",
    "l",
    "d",
    "pour",
    "par",
    "sur",
    "un",
    "une",
    "dans",
    "son",
    "sa",
    "ses",
    "vos",
    "nos",
    "valeur",
    "technique",
    "moyens",
    "mise",
    "place",
}


@dataclass(frozen=True)
class Criterion:
    name: str  # sub-criterion when there is one, else the criterion
    weight: float | None


@dataclass
class PlannedSection:
    title: str
    criterion: str | None = None
    weight: float | None = None
    requirement_refs: list[str] = field(default_factory=list)
    word_budget: int = 0


def _words(text: str) -> set[str]:
    return {w for w in normalize(text).split() if len(w) > 2 and w not in _STOPWORDS}


def flatten_criteria(award_criteria: list[dict[str, object]]) -> list[Criterion]:
    """Sub-criteria when present (they are what the buyer scores), else criteria. Price is
    not part of the memoir."""
    out: list[Criterion] = []
    for c in award_criteria:
        name = str(c.get("name") or "")
        if "prix" in normalize(name) and not c.get("subcriteria"):
            continue
        subs = c.get("subcriteria") or []
        if isinstance(subs, list) and subs:
            for s in subs:
                if isinstance(s, dict) and s.get("name"):
                    out.append(Criterion(str(s["name"]), _float(s.get("weight_pct"))))
        else:
            out.append(Criterion(name, _float(c.get("weight_pct"))))
    return out


def _float(v: object) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


# A chapter: « 1. », « 1 – », « 10) », « II. », « Chapitre 3 : »; not « 2.1 » (a sub-title).
TOP_LEVEL = re.compile(
    r"^\s*(?:chapitre\s+)?(?:\d{1,2}(?![.,]\d)|[IVX]{1,5}(?=[\s.)\-–—:]))\s*[-–—.):]?\s+\S",
    re.IGNORECASE,
)
NUMBER = re.compile(
    r"^\s*(?:chapitre\s+)?(?:\d{1,2}|[IVX]{1,5}(?=[\s.)\-–—:]))\s*[-–—.):]?\s*",
    re.IGNORECASE,
)


def template_outline(headings: list[str]) -> list[str]:
    """Chapter titles of the company's template memoir, in order, without their number:
    the chapters are reordered by the RC's criteria. A chapter met twice (a table of
    contents typed at the top, then the title again in the body) counts once."""
    titles = [h.strip() for h in headings if h and h.strip()]
    top = [h for h in titles if TOP_LEVEL.match(h)]
    chosen = top or titles
    out: dict[str, str] = {}
    for title in chosen:
        bare = NUMBER.sub("", title).strip() if top else title
        if bare:
            out.setdefault(normalize(re.sub(r"\W+", " ", bare)).strip(), bare)
    return list(out.values())


def build_outline(
    imposed: list[str], template: list[str], criteria: list[Criterion]
) -> tuple[str, list[PlannedSection]]:
    """(outline_source, sections) — see module docstring."""
    if imposed:
        sections = [PlannedSection(t) for t in imposed]  # word for word, in order
        source = "rc_imposed"
    elif template:
        sections = [PlannedSection(t) for t in template]
        source = "org_template"
    else:
        sections = [PlannedSection(t) for t in SECTOR_DEFAULT_OUTLINE]
        source = "sector_default"

    for section in sections:
        best, best_score = None, 0
        for c in criteria:
            score = len(_words(section.title) & _words(c.name))
            if score > best_score:
                best, best_score = c, score
        if best is not None:
            section.criterion, section.weight = best.name, best.weight

    if source == "org_template" and criteria:
        # "Réorganisé selon les sous-critères" (US-4.1 CA2): chapters follow the RC's
        # criteria order; chapters matching no criterion keep their relative order, after.
        order = {c.name: i for i, c in enumerate(criteria)}
        sections.sort(
            key=lambda s: order.get(s.criterion, len(order)) if s.criterion else len(order)
        )
    return source, sections


def assign_requirements(
    sections: list[PlannedSection], requirements: list[tuple[str, str, str]]
) -> None:
    """Attach each requirement (ref, category, text) to the chapter that should answer it."""
    for ref, category, text in requirements:
        hints = CATEGORY_HINTS.get(category, CATEGORY_HINTS["other"])
        req_words = _words(text)
        scores = [_fit(s, hints, req_words) for s in sections]
        best = sections[scores.index(max(scores))]  # first best chapter on ties
        if max(scores) == (0, 0):  # nothing matches: the methodology-like or first chapter
            best = next(
                (
                    s
                    for s in sections
                    if any(h in normalize(s.title) for h in CATEGORY_HINTS["other"])
                ),
                sections[0],
            )
        best.requirement_refs.append(ref)


def _fit(section: PlannedSection, hints: tuple[str, ...], req_words: set[str]) -> tuple[int, int]:
    """(category hints found in the title, words shared with the requirement)."""
    title = normalize(section.title)
    return (sum(h in title for h in hints), len(_words(section.title) & req_words))


def words_per_page(font_size: float | None = None) -> int:
    """About 500 words a page in the export's 10.5 pt body; fewer when the RC imposes a bigger
    font (the text area grows with the square of the size)."""
    if not font_size:
        return WORDS_PER_PAGE
    return round(WORDS_PER_PAGE * (BODY_SIZE / font_size) ** 2)


def assign_word_budgets(
    sections: list[PlannedSection], max_pages: int | None, font_size: float | None = None
) -> int:
    """Split the page budget by criterion weight; returns the total word budget."""
    per_page = words_per_page(font_size)
    total = int((max_pages or DEFAULT_PAGES) * per_page * 0.9)  # keep a margin for tables
    weights = [s.weight for s in sections if s.weight]
    default = (sum(weights) / len(weights)) if weights else 1.0
    # A chapter without criterion weighs half an average weighted one; none weighted: equal.
    shares = [(s.weight or default * 0.5) if weights else 1.0 for s in sections]
    unit = total / sum(shares)
    for section, share in zip(sections, shares, strict=True):
        section.word_budget = max(MIN_SECTION_WORDS, round(unit * share / 50.0) * 50)
    return total
