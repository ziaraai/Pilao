"""Feedback from inside the application, and the time saved on bids (P4-02).

Each message is stored with the company's data (exported and erased with it) and, when
``FEEDBACK_EMAIL`` is set, mailed to the team at once: during the test phase, someone
reads every message the same day. A user sends at most ``FEEDBACK_MAX_PER_HOUR``.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.email import Email, Mailer
from app.core.errors import ApiError
from app.db.models import AuditLog, Bid, Feedback, Organization, User
from app.schemas.feedback import FeedbackIn

logger = logging.getLogger("pilao.feedback")
KINDS = {"idea": "Idée", "problem": "Problème", "question": "Question"}


def submit(
    db: Session, user: User, org: Organization, data: FeedbackIn, mailer: Mailer
) -> Feedback:
    """Scoped session: a bid of another company is simply not found (and not linked)."""
    s = get_settings()
    recent = db.scalar(
        select(func.count())
        .select_from(Feedback)
        .where(
            Feedback.user_id == user.id,
            Feedback.created_at >= datetime.now(UTC) - timedelta(hours=1),
        )
    )
    if (recent or 0) >= s.feedback_max_per_hour:
        raise ApiError(
            429,
            "too_many_feedback",
            "Merci ! Vous avez déjà envoyé beaucoup d'avis : réessayez plus tard.",
        )
    bid = db.get(Bid, data.bid_id) if data.bid_id else None
    item = Feedback(
        user_id=user.id,
        kind=data.kind,
        message=data.message.strip(),
        page=(data.page or "").strip()[:300] or None,
        bid_id=bid.id if bid else None,
    )
    db.add(item)
    db.flush()
    db.add(AuditLog(user_id=user.id, action="feedback", entity="feedback", entity_id=item.id))
    db.commit()
    if s.feedback_email:
        try:
            mailer.send(
                Email(
                    to=s.feedback_email,
                    subject=f"[Pilao] {KINDS[item.kind]} — {org.name}",
                    body=(
                        f"{KINDS[item.kind]} de {user.full_name or user.email} ({user.email}), "
                        f"{org.name}\n"
                        f"Page : {item.page or 'non précisée'}"
                        + (f"\nDossier : {bid.title}" if bid else "")
                        + f"\n\n{item.message}\n"
                    ),
                )
            )
        except Exception:  # stored anyway: the report (CLI) still lists it
            logger.exception("could not mail feedback %s", item.id)
    return item


@dataclass
class TimeSaved:
    bids: int = 0  # bids with both durations
    minutes_with: int = 0
    minutes_usual: int = 0

    @property
    def minutes_saved(self) -> int:
        return self.minutes_usual - self.minutes_with


def time_saved(db: Session) -> TimeSaved:
    """Over the bids where both durations are filled in (scoped: this company only)."""
    count, with_, usual = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(Bid.minutes_with_pilao), 0),
            func.coalesce(func.sum(Bid.minutes_usual), 0),
        ).where(Bid.minutes_with_pilao.is_not(None), Bid.minutes_usual.is_not(None))
    ).one()
    return TimeSaved(int(count or 0), int(with_ or 0), int(usual or 0))


# --- Every company at once: the team's report and the administration (unscoped session) ---


@dataclass(frozen=True)
class FeedbackRow:
    created_at: datetime
    org_name: str
    user_email: str | None  # None: the account was removed since
    kind: str
    page: str | None
    message: str


@dataclass(frozen=True)
class TimeSavedRow:
    org_name: str
    bids: int  # bids with both durations
    minutes_with: int
    minutes_usual: int

    @property
    def minutes_saved(self) -> int:
        return self.minutes_usual - self.minutes_with


def recent_feedback(
    db: Session, since: datetime | None = None, org_id: uuid.UUID | None = None
) -> list[FeedbackRow]:
    """What the users wrote, the most recent first; one company with ``org_id``."""
    query = (
        select(Feedback, Organization.name, User.email)
        .join(Organization, Organization.id == Feedback.org_id)
        .outerjoin(User, User.id == Feedback.user_id)
        .order_by(Feedback.created_at.desc())
    )
    if since is not None:
        query = query.where(Feedback.created_at >= since)
    if org_id is not None:
        query = query.where(Feedback.org_id == org_id)
    return [
        FeedbackRow(item.created_at, org, email, item.kind, item.page, item.message)
        for item, org, email in db.execute(query).all()
    ]


def time_saved_by_org(db: Session) -> list[TimeSavedRow]:
    """Per company, over the bids where both durations are filled in."""
    rows = db.execute(
        select(
            Organization.name,
            func.count(),
            func.coalesce(func.sum(Bid.minutes_with_pilao), 0),
            func.coalesce(func.sum(Bid.minutes_usual), 0),
        )
        .join(Organization, Organization.id == Bid.org_id)
        .where(Bid.minutes_with_pilao.is_not(None), Bid.minutes_usual.is_not(None))
        .group_by(Organization.id, Organization.name)
        .order_by(Organization.name)
    ).all()
    return [
        TimeSavedRow(name, int(n), int(with_ or 0), int(usual or 0))
        for name, n, with_, usual in rows
    ]
