"""« Plateformes des DCE » (admin, 24/11): on which buyers' platforms the DCE of the notices
and of the dossiers are, and how Pilao gets them (robot, guided, no link). Read-only."""

import uuid
from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Bid, Tender, TenderMatch
from app.domain.dce_sources import platform_group, recognize
from app.schemas.admin import DcePlatformRowOut, DcePlatformsOut

MAX_ROWS = 20  # the other sites are added up on one line
OTHERS = "Autres sites"


def _count(links: Iterable[str | None]) -> tuple[Counter[str], dict[str, str]]:
    counts: Counter[str] = Counter()
    retrieval: dict[str, str] = {}
    for link in links:
        label, how = platform_group(recognize(link))
        counts[label] += 1
        retrieval[label] = how
    return counts, retrieval


def dce_platforms(
    db: Session, now: datetime, days: int, org_id: uuid.UUID | None = None
) -> DcePlatformsOut:
    """Notices published over ``days`` (all companies), the ones retained for a company (or
    all of them) and the dossiers created over the same days, by platform of their DCE link."""
    since = now - timedelta(days=days)
    notices, how_n = _count(
        db.scalars(
            select(Tender.documents_url).where(
                Tender.published_at >= since, Tender.duplicate_of.is_(None)
            )
        )
    )
    matched_q = (
        select(Tender.documents_url)
        .join(TenderMatch, TenderMatch.tender_id == Tender.id)
        .where(Tender.published_at >= since)
    )
    bids_q = (
        select(Bid.dce_url, Tender.documents_url)
        .outerjoin(Tender, Tender.id == Bid.tender_id)
        .where(Bid.created_at >= since)
    )
    if org_id is not None:
        matched_q = matched_q.where(TenderMatch.org_id == org_id)
        bids_q = bids_q.where(Bid.org_id == org_id)
    matched, how_m = _count(db.scalars(matched_q))
    # the link pasted in the dossier, else the notice's (as « Récupérer le DCE » does)
    dossiers, how_d = _count(own or notice for own, notice in db.execute(bids_q).all())
    retrieval = {**how_n, **how_m, **how_d}

    labels = sorted(
        retrieval,
        key=lambda k: (-dossiers[k], -matched[k], -notices[k], k),
    )
    rows = [
        DcePlatformRowOut(
            platform=k,
            retrieval=retrieval[k],
            notices=notices[k],
            matched=matched[k],
            dossiers=dossiers[k],
        )
        for k in labels[:MAX_ROWS]
    ]
    rest = labels[MAX_ROWS:]
    if rest:
        rows.append(
            DcePlatformRowOut(
                platform=OTHERS,
                retrieval="guided",
                notices=sum(notices[k] for k in rest),
                matched=sum(matched[k] for k in rest),
                dossiers=sum(dossiers[k] for k in rest),
            )
        )
    return DcePlatformsOut(
        days=days,
        org_id=org_id,
        rows=rows,
        totals={
            "notices": sum(notices.values()),
            "matched": sum(matched.values()),
            "dossiers": sum(dossiers.values()),
            "robot_dossiers": sum(n for k, n in dossiers.items() if retrieval[k] == "robot"),
        },
    )
