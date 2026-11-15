"""« Ce qu'il manque » (ADR-048): the missing items of a dossier, computed when read.

The list is never stored: it is read from the text of the latest memoir's chapters (their
``[À COMPLÉTER : …]`` markers) and from the latest pre-filled documents (DC1/DC2, lists of
means…), so it is right even after a chapter was edited by hand. Answering in place and
removing a sentence change the chapters without the AI (a revision « edited »); completing
with the AI is ``app.services.marker_fill``.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import exists, literal, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db.models import (
    AuditLog,
    Bid,
    CompanyReference,
    Equipment,
    GeneratedDocument,
    HumanResource,
    MarkerFill,
    Memoir,
    MemoirSection,
    Organization,
    User,
)
from app.domain.memoir_checks import flag_dicts, flags_after_edit, force_title
from app.domain.missing import KINDS, MissingKind, answer, classify, marker_key, markers, remove
from app.exports.dc_forms import FORMS
from app.schemas.missing import (
    MissingFillOut,
    MissingItemOut,
    MissingOut,
    MissingSectionOut,
    ProfileGapsOut,
)
from app.services.documents import generate_form
from app.services.memoir_editing import add_revision, mark_matrix_stale
from app.storage.objects import ObjectStorage

BUSY_MESSAGE = "Un chapitre est en cours de rédaction : réessayez dans un instant."


def latest_memoir(db: Session, bid: Bid) -> Memoir | None:
    return db.scalars(
        select(Memoir).where(Memoir.bid_id == bid.id).order_by(Memoir.version.desc())
    ).first()


def memoir_busy(db: Session, memoir: Memoir | None) -> bool:
    if memoir is None:
        return False
    if memoir.status == "generating":
        return True
    return (
        db.scalar(
            select(literal(True))
            .where(MemoirSection.memoir_id == memoir.id, MemoirSection.status == "generating")
            .limit(1)
        )
        is not None
    )


def _sections(db: Session, memoir: Memoir) -> list[MemoirSection]:
    return list(
        db.scalars(
            select(MemoirSection)
            .where(MemoirSection.memoir_id == memoir.id)
            .order_by(MemoirSection.position)
        )
    )


def latest_documents(db: Session, bid: Bid) -> dict[str, GeneratedDocument]:
    """The latest ready document of each pre-filled kind, in the order of ``FORMS``."""
    latest: dict[str, GeneratedDocument] = {}
    for doc in db.scalars(
        select(GeneratedDocument)
        .where(GeneratedDocument.bid_id == bid.id, GeneratedDocument.kind.in_(list(FORMS)))
        .order_by(GeneratedDocument.created_at.desc())
    ):
        latest.setdefault(doc.kind, doc)
    return {k: latest[k] for k in FORMS if k in latest and latest[k].status == "ready"}


@dataclass
class _Item:
    key: str
    text: str
    order: tuple[int, int]
    kind: MissingKind | None = None
    sections: list[MemoirSection] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)


def _items(db: Session, bid: Bid, memoir: Memoir | None) -> list[_Item]:
    found: dict[str, _Item] = {}
    if memoir is not None:
        for section in _sections(db, memoir):
            drawers = {
                marker_key(str(f.get("text") or "")): f["kind"]
                for f in section.flags
                if f.get("type") == "to_complete" and f.get("kind") in KINDS
            }
            for m in markers(section.content_md or ""):
                item = found.setdefault(m.key, _Item(m.key, m.text, (section.position, m.start)))
                if section not in item.sections:
                    item.sections.append(section)
                if item.kind is None and m.key in drawers:
                    item.kind = drawers[m.key]
    for n, (kind, doc) in enumerate(latest_documents(db, bid).items()):
        for i, text in enumerate(doc.to_complete):
            drawer = classify(text)
            if drawer == "tender":
                continue  # the buyer's name, the signature: not something the profile gives
            key = marker_key(text)
            item = found.setdefault(key, _Item(key, text, (10_000 + n, i), drawer))
            if kind not in item.documents:
                item.documents.append(kind)
    for item in found.values():
        if item.kind is None:
            item.kind = classify(item.text)

    def rank(item: _Item) -> tuple[int, int, tuple[int, int]]:
        group = KINDS.index(item.kind or "tender") if item.sections else len(KINDS)
        return group, -len(item.sections), item.order

    return sorted(found.values(), key=rank)


def _fills(db: Session, memoir: Memoir | None) -> dict[str, MarkerFill]:
    if memoir is None:
        return {}
    latest: dict[str, MarkerFill] = {}
    for fill in db.scalars(
        select(MarkerFill)
        .where(MarkerFill.memoir_id == memoir.id)
        .order_by(MarkerFill.created_at.desc())
    ):
        latest.setdefault(fill.key, fill)
    return latest


def _has(
    db: Session,
    model: type[HumanResource] | type[Equipment] | type[CompanyReference],
    org_id: uuid.UUID,
) -> bool:
    return bool(db.scalar(select(exists().where(model.org_id == org_id))))


def missing_for_bid(db: Session, bid: Bid) -> MissingOut:
    memoir = latest_memoir(db, bid)
    fills = _fills(db, memoir)
    items = [
        MissingItemOut(
            key=item.key,
            text=item.text,
            kind=item.kind or "tender",
            sections=[MissingSectionOut(id=s.id, title=s.title) for s in item.sections],
            documents=item.documents,
            fill=(
                MissingFillOut(status=f.status, outcome=f.outcome, error=f.error)
                if (f := fills.get(item.key)) is not None
                else None
            ),
        )
        for item in _items(db, bid, memoir)
    ]
    return MissingOut(
        memoir_id=memoir.id if memoir else None,
        memoir_busy=memoir_busy(db, memoir),
        items=items,
        profile_gaps=ProfileGapsOut(
            staff=not _has(db, HumanResource, bid.org_id),
            equipment=not _has(db, Equipment, bid.org_id),
            references=not _has(db, CompanyReference, bid.org_id),
        ),
    )


def missing_count(db: Session, bid: Bid) -> int:
    return len(_items(db, bid, latest_memoir(db, bid)))


def _change(
    db: Session, user: User, bid: Bid, key: str, change: Callable[[str], str], action: str
) -> MissingOut:
    """Apply ``change`` to every chapter of the latest memoir that holds a marker of ``key``:
    a revision « edited » each, the matrix flagged as outdated. A key found nowhere (the
    chapter was edited meanwhile) changes nothing."""
    memoir = latest_memoir(db, bid)
    if memoir is not None:
        if memoir_busy(db, memoir):
            raise ApiError(409, "memoir_busy", BUSY_MESSAGE)
        changed = False
        for section in _sections(db, memoir):
            locked = db.get(MemoirSection, section.id, with_for_update=True, populate_existing=True)
            if locked is None or not any(m.key == key for m in markers(locked.content_md or "")):
                continue
            if locked.status == "generating":
                raise ApiError(409, "memoir_busy", BUSY_MESSAGE)
            body = force_title(change(locked.content_md or ""), locked.title)
            if body == locked.content_md:
                continue
            locked.content_md = body
            locked.flags = flag_dicts(flags_after_edit(body, locked.flags, locked.word_budget))
            locked.status, locked.error, locked.edited_by_user = "ready", None, True
            add_revision(db, locked, "edited", user.id)
            db.add(
                AuditLog(
                    user_id=user.id,
                    action=action,
                    entity="memoir_section",
                    entity_id=locked.id,
                    meta={"key": key, "revision": locked.revision},
                )
            )
            changed = True
        if changed:
            mark_matrix_stale(memoir)
        db.commit()
    return missing_for_bid(db, bid)


def answer_marker(db: Session, user: User, bid: Bid, key: str, value: str) -> MissingOut:
    text = value.strip()
    if not text:
        raise ApiError(422, "empty_answer", "Écrivez la réponse avant de valider.")
    return _change(db, user, bid, key, lambda md: answer(md, key, text), "complete_marker")


def remove_marker(db: Session, user: User, bid: Bid, key: str) -> MissingOut:
    return _change(db, user, bid, key, lambda md: remove(md, key), "remove_marker")


def regenerate_documents(
    db: Session, org: Organization, user: User, bid: Bid, storage: ObjectStorage
) -> MissingOut:
    """After the profile was completed: every pre-filled document that still lacks something
    the profile gives is built again (free, a few milliseconds)."""
    for kind, doc in latest_documents(db, bid).items():
        if any(classify(t) != "tender" for t in doc.to_complete):
            generate_form(db, org, user, bid, kind, storage)
    db.commit()
    return missing_for_bid(db, bid)
