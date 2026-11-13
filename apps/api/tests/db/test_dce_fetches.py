import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Bid, DceFetch
from tests.db.test_tenancy import make_org


def _bid(db: Session) -> Bid:
    org = make_org(db, 77)
    bid = Bid(org_id=org.id, title="Nettoyage des écoles")
    db.add(bid)
    db.flush()
    return bid


def _fetch(bid: Bid, kind: str = "retrieval", status: str = "pending") -> DceFetch:
    return DceFetch(org_id=bid.org_id, bid_id=bid.id, kind=kind, status=status, site="PLACE")


def test_one_active_fetch_per_bid(db: Session) -> None:
    bid = _bid(db)
    db.add(_fetch(bid))
    db.flush()
    with db.begin_nested():
        db.add(_fetch(bid, kind="update"))
        with pytest.raises(IntegrityError):
            db.flush()
    db.add(_fetch(bid, kind="check", status="running"))  # a daily check never blocks
    db.flush()
    other = _bid_done(db, bid)
    assert other is not None


def _bid_done(db: Session, bid: Bid) -> DceFetch:
    """A finished attempt and a new one live side by side."""
    first = db.scalars(select(DceFetch).where(DceFetch.kind == "retrieval")).one()
    first.status = "done"
    db.flush()
    again = _fetch(bid)
    db.add(again)
    db.flush()
    return again


def test_fetches_follow_their_bid(db: Session) -> None:
    bid = _bid(db)
    db.add(_fetch(bid, status="done"))
    db.flush()
    db.delete(bid)
    db.flush()
    db.expire_all()
    assert db.scalars(select(DceFetch)).all() == []
