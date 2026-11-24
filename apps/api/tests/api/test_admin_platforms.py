"""« Plateformes des DCE » (admin, 24/11): where the DCE of the notices and dossiers are, to know
where the robot or the e-mail address would bring the most."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Tender, TenderMatch
from tests.api.admin_helpers import activated_admin, org_named, seed_bid
from tests.api.helpers import signed_in_client
from tests.conftest import Outbox

Factory = Callable[[], TestClient]
PLACE = "https://www.marches-publics.gouv.fr/entreprise/consultation/{n}?orgAcronyme=a1b"
AWS = "https://www.marches-publics.info/mpiaws/index.cfm?IDM={n}"


def tender(db: Session, n: int, url: str | None, days_ago: int = 5) -> Tender:
    t = Tender(
        source="boamp",
        source_id=f"P-{n}",
        title=f"Nettoyage {n}",
        documents_url=url.format(n=n) if url else None,
        published_at=datetime.now(UTC) - timedelta(days=days_ago),
    )
    db.add(t)
    db.flush()
    return t


def rows(body: dict[str, Any]) -> dict[str, tuple[str, int, int, int]]:
    return {
        r["platform"]: (r["retrieval"], r["notices"], r["matched"], r["dossiers"])
        for r in body["rows"]
    }


def test_platforms_count_notices_matches_and_dossiers(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    signed_in_client(make_client, outbox, 1)
    signed_in_client(make_client, outbox, 2)
    one, two = org_named(db, "Entreprise 1").id, org_named(db, "Entreprise 2").id
    place = [tender(db, n, PLACE) for n in range(3)]
    aws = [tender(db, n, AWS) for n in range(10, 12)]
    tender(db, 20, None)
    tender(db, 30, AWS, days_ago=200)  # too old for the 90 days
    for t in (place[0], aws[0], aws[1]):
        db.add(TenderMatch(org_id=one, tender_id=t.id))
    db.add(TenderMatch(org_id=two, tender_id=place[1].id))
    seed_bid(db, one, tender_id=aws[0].id)  # the notice's link
    seed_bid(db, one, dce_url=AWS.format(n=99))  # a link pasted in the dossier
    seed_bid(db, two, dce_url=PLACE.format(n=7))
    seed_bid(db, two)  # no link at all
    db.commit()
    admin, _ = activated_admin(make_client, db)

    body = admin.get("/admin/dce-platforms").json()
    assert body["days"] == 90
    assert rows(body) == {
        "AWS (marches-publics.info)": ("guided", 2, 2, 2),
        "PLACE": ("robot", 3, 2, 1),
        "Sans lien vers le DCE": ("none", 1, 0, 1),
    }
    assert body["rows"][0]["platform"] == "AWS (marches-publics.info)"  # most used
    assert body["totals"] == {"notices": 6, "matched": 4, "dossiers": 4, "robot_dossiers": 1}

    mine = admin.get("/admin/dce-platforms", params={"org_id": str(one)}).json()
    assert rows(mine) == {
        "AWS (marches-publics.info)": ("guided", 2, 2, 2),
        "PLACE": ("robot", 3, 1, 0),
        "Sans lien vers le DCE": ("none", 1, 0, 0),
    }
    assert (
        admin.get("/admin/dce-platforms", params={"days": 365}).json()["rows"][0]["notices"] == 3
    )  # the old AWS notice counts over a year
    assert admin.get("/admin/dce-platforms", params={"days": 12}).status_code == 422


def test_platforms_are_for_the_super_admin_only(make_client: Factory, outbox: Outbox) -> None:
    company = signed_in_client(make_client, outbox, 1)
    assert company.get("/admin/dce-platforms").status_code in (401, 403)
