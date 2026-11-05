"""Chapter editing and history (US-4.4, P2-05).

Every text a chapter receives (drafted by the model, edited by the user, restored from the
history) becomes a numbered revision. An edit names the revision it started from: if the
chapter changed meanwhile (regeneration, a colleague's edit), it is refused rather than
silently overwriting the newer text.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import AuditLog, Memoir, MemoirSection, MemoirSectionRevision, User
from app.domain.memoir_checks import flags_after_edit, force_title

MAX_CHAPTER_CHARS = 60_000


def add_revision(
    db: Session,
    section: MemoirSection,
    origin: str,
    user_id: uuid.UUID | None,
    instruction: str | None = None,
) -> MemoirSectionRevision:
    """Record the section's current text as its next revision (the caller holds its lock)."""
    section.revision += 1
    revision = MemoirSectionRevision(
        org_id=section.org_id,
        section_id=section.id,
        revision=section.revision,
        origin=origin,
        content_md=section.content_md or "",
        flags=section.flags,
        sources=section.sources,
        covered_refs=section.covered_refs,
        instruction=instruction,
        model=section.generated_by_model if origin == "generated" else None,
        prompt_version=section.prompt_version if origin == "generated" else None,
        created_by=user_id,
    )
    db.add(revision)
    return revision


def mark_matrix_stale(memoir: Memoir) -> None:
    """The text changed after the check: the matrix is kept, flagged as outdated."""
    if memoir.conformity_status in ("ready", "error"):
        memoir.conformity_status = "stale"


def _editable(
    db: Session, section: MemoirSection, base_revision: int
) -> tuple[Memoir, MemoirSection]:
    locked = db.get_one(MemoirSection, section.id, populate_existing=True, with_for_update=True)
    memoir = db.get_one(Memoir, locked.memoir_id)
    if memoir.status == "draft":
        raise ApiError(409, "memoir_not_generated", "Lancez d'abord la rédaction du mémoire.")
    if locked.status in ("pending", "generating"):
        raise ApiError(409, "section_busy", "Ce chapitre est en cours de rédaction.")
    if locked.revision != base_revision:
        raise ApiError(
            409,
            "edit_conflict",
            "Ce chapitre a changé depuis que vous l'avez ouvert (nouvelle rédaction ou autre "
            "modification). Votre texte n'a pas été enregistré : copiez-le, puis rechargez.",
        )
    return memoir, locked


def edit_section(
    db: Session, user: User, section: MemoirSection, body_md: str, base_revision: int
) -> MemoirSection:
    """US-4.4 CA1. The planned title is kept: the user edits the body of the chapter."""
    body = body_md.strip()
    if not body:
        raise ApiError(422, "empty_chapter", "Le chapitre ne peut pas être vide.")
    if len(body) > MAX_CHAPTER_CHARS:
        raise ApiError(422, "chapter_too_long", "Chapitre trop long (60 000 caractères maximum).")
    memoir, locked = _editable(db, section, base_revision)
    locked.content_md = force_title(body, locked.title)
    locked.flags = [
        {"type": f.type, "text": f.text, "term": f.term}
        for f in flags_after_edit(locked.content_md, locked.flags, locked.word_budget)
    ]
    locked.status, locked.error, locked.edited_by_user = "ready", None, True
    add_revision(db, locked, "edited", user.id)
    mark_matrix_stale(memoir)
    db.add(
        AuditLog(
            user_id=user.id,
            action="edit",
            entity="memoir_section",
            entity_id=locked.id,
            meta={"revision": locked.revision},
        )
    )
    db.commit()
    return locked


def restore_revision(
    db: Session, user: User, section: MemoirSection, revision_id: uuid.UUID, base_revision: int
) -> MemoirSection:
    old = db.scalar(
        select(MemoirSectionRevision).where(
            MemoirSectionRevision.id == revision_id,
            MemoirSectionRevision.section_id == section.id,
        )
    )
    if old is None:
        raise ApiError(404, "not_found", "Version introuvable.")
    memoir, locked = _editable(db, section, base_revision)
    locked.content_md, locked.flags = old.content_md, old.flags
    locked.sources, locked.covered_refs = old.sources, old.covered_refs
    locked.status, locked.error = "ready", None
    locked.edited_by_user = old.origin != "generated"
    add_revision(db, locked, "restored", user.id)
    mark_matrix_stale(memoir)
    db.add(
        AuditLog(
            user_id=user.id,
            action="restore",
            entity="memoir_section",
            entity_id=locked.id,
            meta={"from_revision": old.revision, "revision": locked.revision},
        )
    )
    db.commit()
    return locked
