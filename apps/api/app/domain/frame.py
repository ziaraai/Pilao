"""The buyer's memoir frame (ADR-051): find it in the DCE, and place each chapter in it.

A frame (« cadre de mémoire technique », « cadre de réponse ») is a Word file the buyer wants
back, completed: its boxes name what will be graded. Each chapter of the memoir goes under
the box it answers. Titles are compared word by word, without the words most chapter titles
share (« au regard du mémoire technique remis par le candidat »); what is left unmatched is
paired by order when the counts agree, and anything still unmatched is added at the end.
"""

import re
import unicodedata
from dataclasses import dataclass
from itertools import pairwise

MIN_SCORE = 0.4
_STOP = {
    "les", "des", "une", "pour", "par", "aux", "avec", "dans", "sur", "est", "son", "ses",
    "leur", "leurs", "que", "qui", "ainsi", "entre", "lors", "dont", "cette", "ces", "the",
}  # fmt: skip
# Words of the same family: « développement durable » answers an « environnement » box
_FAMILIES = {
    "#env": {
        "environnement", "environnemental", "environnementale", "durable", "ecologique",
        "ecoresponsable", "dechets", "ecolabel", "biodegradable", "rse",
    },
    "#staff": {
        "humains", "humaines", "personnel", "effectif", "effectifs", "equipe", "equipes",
        "agents", "encadrement",
    },
    "#method": {"methodologie", "methode", "methodes", "protocole", "protocoles"},
    "#quality": {"qualite", "controle", "controles"},
    "#safety": {"securite", "hygiene", "prevention", "epi"},
    "#means": {"materiel", "materiels", "equipements", "machines", "produits"},
    "#planning": {"planning", "calendrier", "delai", "delais", "demarrage"},
}  # fmt: skip
LOOSE_SCORE = 0.1  # within a gap only: a shared family is enough, to be checked
_TOKEN = re.compile(r"\d+(?:[.,]\d+)+|[a-z0-9]+")
_ESCAPED = re.compile(r"#U([0-9A-Fa-f]{4})")


def plain_name(path: str) -> str:
    """« DCE/26020M_M#U00e9moire technique.docx » → « 26020m mémoire technique » (some ZIP
    tools write é as #U00e9)."""
    name = path.rsplit("/", 1)[-1]
    name = name.rsplit(".", 1)[0] if "." in name else name
    name = _ESCAPED.sub(lambda m: chr(int(m.group(1), 16)), name)
    return re.sub(r"[\s_\-]+", " ", name).strip().lower()


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def is_frame_name(path: str) -> bool:
    """A Word file whose name says it is the frame to complete (a PDF cannot be filled)."""
    if not path.lower().endswith(".docx"):
        return False
    name = _fold(plain_name(path))
    return bool(re.search(r"\bcadre\b|\bmemoire\b|reponse technique", name))


def tokens(text: str) -> set[str]:
    words = _TOKEN.findall(_fold(text))
    kept = {w for w in words if (len(w) >= 3 or any(c.isdigit() for c in w)) and w not in _STOP}
    return kept | {family for family, members in _FAMILIES.items() if kept & members}


@dataclass(frozen=True)
class Match:
    anchor: int | None  # index in the anchors, None: added at the end
    uncertain: bool = False  # paired by its place or a family of words: to check


def _score(chapter: set[str], anchor: set[str], weight: dict[str, float]) -> float:
    shared = sum(weight.get(t, 1.0) for t in chapter & anchor)
    total = sum(weight.get(t, 1.0) for t in chapter) + sum(weight.get(t, 1.0) for t in anchor)
    return 2 * shared / total if total else 0.0


def match_chapters(chapters: list[str], anchors: list[str], boxes: list[int]) -> list[Match]:
    """``anchors``: the texts of the frame that can head an answer, in document order;
    ``boxes``: those that are answer boxes (tables), used to pair what is left by order."""
    chapter_tokens = [tokens(c) for c in chapters]
    anchor_tokens = [tokens(a) for a in anchors]
    seen: dict[str, int] = {}
    for toks in chapter_tokens:
        for t in toks:
            seen[t] = seen.get(t, 0) + 1
    # words shared by several chapter titles say nothing about which box is which
    weight = {t: (1.0 if n == 1 else 0.2) for t, n in seen.items()}
    pairs = sorted(
        (
            (_score(ct, at, weight), i, j)
            for i, ct in enumerate(chapter_tokens)
            for j, at in enumerate(anchor_tokens)
        ),
        key=lambda p: (-p[0], p[1], p[2]),
    )
    chosen: dict[int, int] = {}
    for score, i, j in pairs:
        if score < MIN_SCORE:
            break
        if i in chosen or j in chosen.values():
            continue
        # never across another pair: a later chapter stays below an earlier one's box
        if any((i < k) != (j < chosen[k]) for k in chosen):
            continue
        chosen[i] = j
    result = {i: Match(j) for i, j in chosen.items()}
    # what is left between two placed chapters: paired with the boxes left in the same gap,
    # by order when the counts agree, otherwise by a family of words
    bounds = [(-1, -1), *sorted(chosen.items()), (len(chapters), len(anchors))]
    for (i0, j0), (i1, j1) in pairwise(bounds):
        left = [i for i in range(i0 + 1, i1) if i not in chosen]
        free = [b for b in boxes if j0 < b < j1 and b not in chosen.values()]
        if not left:
            continue
        if free and len(left) == len(free):
            for i, b in zip(left, free, strict=True):
                result[i] = Match(b, uncertain=True)
            continue
        # otherwise any title of the frame left in the gap (« Valeur technique »), by its words
        spots = [j for j in range(j0 + 1, j1) if j not in chosen.values()]
        loose = sorted(
            (
                (_score(chapter_tokens[i], anchor_tokens[b], weight), i, b)
                for i in left
                for b in spots
            ),
            key=lambda p: (-p[0], p[1], p[2]),
        )
        taken: dict[int, int] = {}
        for score, i, b in loose:
            if score < LOOSE_SCORE:
                break
            if i in taken or b in taken.values() or any((i < k) != (b < taken[k]) for k in taken):
                continue
            taken[i] = b
            result[i] = Match(b, uncertain=True)
    return [result.get(i, Match(None)) for i in range(len(chapters))]
