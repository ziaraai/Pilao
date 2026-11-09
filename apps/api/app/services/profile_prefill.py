"""Pre-filling the profile from the company's own documents (US-1.6, spec 2026-11-09).

A background job reads every indexed document of the knowledge base, asks the model for the
staff, equipment, certifications and references written in it, checks each line against the
document (app/domain/profile_prefill.py) and stores what is left as proposals. Nothing joins
the profile until the user accepts it.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DocumentChunk, KnowledgeDocument
from app.domain.dce import normalize
from app.domain.profile_prefill import Passage

PROMPT = "extraction_profil"
TASK = "profile_extraction"
MAX_CHARS = 60_000  # above this, only the passages about means and references are sent
TOPICS = (
    "moyen",
    "personnel",
    "effectif",
    "equipe",
    "materiel",
    "equipement",
    "machine",
    "client",
    "reference",
    "chantier",
    "certif",
    "qualif",
    "label",
)


def document_passages(db: Session, doc: KnowledgeDocument) -> list[Passage]:
    """The document's indexed passages, in order (no new extraction of the file)."""
    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.source_type == "knowledge", DocumentChunk.source_id == doc.id)
        .order_by(DocumentChunk.position)
    )
    return [Passage(c.content, c.page_from, c.heading) for c in chunks]


def _neutralize(text: str) -> str:
    """A document must not be able to close its own tag (prompt injection)."""
    return text.replace("<profile_document", "‹profile_document").replace(
        "</profile_document", "‹/profile_document"
    )


def render_passages(passages: list[Passage]) -> str:
    """The text sent to the model: ``[p. N]`` when the page changes, ``## heading`` when the
    part changes, then the passage."""
    lines: list[str] = []
    page: int | None = None
    heading: str | None = None
    for p in passages:
        if p.page is not None and p.page != page:
            lines.append(f"[p. {p.page}]")
            page = p.page
        if p.heading and p.heading != heading:
            lines.append(f"## {_neutralize(p.heading)}")
            heading = p.heading
        lines.append(_neutralize(p.content))
    return "\n".join(lines)


def select_passages(passages: list[Passage], max_chars: int = MAX_CHARS) -> list[Passage]:
    """Everything if it fits; otherwise the passages about staff, equipment, clients,
    references or certifications, in the document's order, up to ``max_chars``."""
    if len(render_passages(passages)) <= max_chars:
        return passages
    kept: list[Passage] = []
    size = 0
    for p in passages:
        if not any(t in normalize(f"{p.heading or ''} {p.content}") for t in TOPICS):
            continue
        cost = len(render_passages([p])) + 1  # an upper bound: page and heading marks repeat
        if size + cost > max_chars:
            break
        kept.append(p)
        size += cost
    return kept
