"""The DCE retrieval routes (spec « Récupération des DCE », § 7.5)."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Organization
from tests.api.test_dce_retrieval_service import PLACE, World
from tests.conftest import FakeQueue, FakeRobot, Outbox

AWS = "https://www.marches-publics.info/mpiaws/index.cfm?fuseaction=dematEnt.login&IDM=1878216"


def test_source_of_a_notice(make_client: Any, outbox: Outbox, db: Session) -> None:
    w = World(make_client, outbox, db)
    res = w.client.get(f"/bids/{w.bid_id}/dce/source")
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["url"], body["platform"], body["site"]) == (PLACE, "atexo", "PLACE")
    assert body["automatic"] is True and body["home_only"] is False
    assert body["robot_enabled"] is True
    assert body["terms_url"] == (
        "https://www.marches-publics.gouv.fr/entreprise/footer/conditions-utilisation"
    )
    assert body["mode"] is None
    assert body["contact"] == {"first_name": None, "last_name": None, "email": None}
    assert body["last_fetch"] is None and body["watch"] is None


def test_source_without_a_link(make_client: Any, outbox: Outbox, db: Session) -> None:
    w = World(make_client, outbox, db)
    w.bid.tender_id = None
    db.commit()
    body = w.client.get(f"/bids/{w.bid_id}/dce/source").json()
    assert (body["url"], body["platform"], body["automatic"]) == (None, None, False)
    assert body["guide"] == []


def test_paste_a_link(make_client: Any, outbox: Outbox, db: Session) -> None:
    w = World(make_client, outbox, db)
    res = w.client.put(f"/bids/{w.bid_id}/dce/source", json={"url": AWS})
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["platform"], body["automatic"]) == ("aws", False)
    assert len(body["guide"]) == 3
    bad = w.client.put(f"/bids/{w.bid_id}/dce/source", json={"url": "pas un lien"})
    assert bad.status_code == 422
    assert bad.json()["error"] == {
        "code": "bad_link",
        "message": "Collez un lien qui commence par https://",
    }


def test_retrieve_then_follow_it(
    make_client: Any, outbox: Outbox, db: Session, queue: FakeQueue
) -> None:
    w = World(make_client, outbox, db)
    first = w.client.post(f"/bids/{w.bid_id}/dce/retrieve", json={})
    assert first.status_code == 409
    assert first.json()["error"]["code"] == "retrieval_choice_needed"
    incomplete = w.client.post(f"/bids/{w.bid_id}/dce/retrieve", json={"mode": "identified"})
    assert (incomplete.status_code, incomplete.json()["error"]["code"]) == (
        422,
        "contact_incomplete",
    )
    res = w.client.post(
        f"/bids/{w.bid_id}/dce/retrieve",
        json={
            "mode": "identified",
            "remember": True,
            "contact": {"first_name": "Sabrina", "last_name": "Martin", "email": "s@example.fr"},
        },
    )
    assert res.status_code == 202, res.text
    assert (res.json()["status"], res.json()["kind"], res.json()["mode"]) == (
        "pending",
        "retrieval",
        "identified",
    )
    again = w.client.post(f"/bids/{w.bid_id}/dce/retrieve", json={})
    assert (again.status_code, again.json()["error"]["code"]) == (409, "retrieval_running")
    source = w.client.get(f"/bids/{w.bid_id}/dce/source").json()
    assert source["last_fetch"]["status"] == "pending"
    assert source["mode"] == "identified"
    queue.drain_fetches(FakeRobot())
    queue.drain_dce()
    source = w.client.get(f"/bids/{w.bid_id}/dce/source").json()
    assert source["last_fetch"]["outcome"] == "ok"
    assert source["watch"]["size_label"] == "0,01 Mo"
    [version] = w.client.get(f"/bids/{w.bid_id}/dce").json()
    assert (version["origin"], version["source_url"]) == ("retrieval", PLACE)
    assert version["uploaded_by_name"] == "User 1"


def test_home_link_is_not_retrieved(make_client: Any, outbox: Outbox, db: Session) -> None:
    w = World(make_client, outbox, db)
    w.client.put(
        f"/bids/{w.bid_id}/dce/source",
        json={"url": "https://www.marches-publics.gouv.fr/?page=Entreprise.AccueilEntreprise"},
    )
    res = w.client.post(f"/bids/{w.bid_id}/dce/retrieve", json={"mode": "anonymous"})
    assert (res.status_code, res.json()["error"]["code"]) == (422, "not_automatic")


def test_company_settings(make_client: Any, outbox: Outbox, db: Session) -> None:
    w = World(make_client, outbox, db)
    assert w.client.get("/profile/dce-retrieval").json() == {
        "mode": None,
        "contact": {"first_name": None, "last_name": None, "email": None},
    }
    body = {
        "mode": "anonymous",
        "contact": {"first_name": "Sabrina", "last_name": "Martin", "email": "s@example.fr"},
    }
    res = w.client.put("/profile/dce-retrieval", json=body)
    assert res.status_code == 200, res.text
    assert res.json() == body
    bad = w.client.put(
        "/profile/dce-retrieval",
        json={"mode": "anonymous", "contact": {"first_name": "A", "last_name": "B", "email": "x"}},
    )
    assert bad.status_code == 422
    wrong_mode = w.client.put("/profile/dce-retrieval", json={"mode": "toujours", "contact": {}})
    assert wrong_mode.status_code == 422


def test_routes_need_the_module(make_client: Any, outbox: Outbox, db: Session) -> None:
    w = World(make_client, outbox, db)
    org = db.get_one(Organization, w.org.id)
    org.modules = ["veille"]
    db.commit()
    base = f"/bids/{w.bid_id}/dce"
    for method, path, body in (
        ("get", f"{base}/source", None),
        ("put", f"{base}/source", {"url": PLACE}),
        ("post", f"{base}/retrieve", {"mode": "anonymous"}),
        ("get", "/profile/dce-retrieval", None),
        ("put", "/profile/dce-retrieval", {"mode": None, "contact": {}}),
    ):
        res = getattr(w.client, method)(path, **({"json": body} if body is not None else {}))
        assert res.status_code == 403, (method, path, res.text)


def test_another_company_dossier(make_client: Any, outbox: Outbox, db: Session) -> None:
    a = World(make_client, outbox, db, 1)
    b = World(make_client, outbox, db, 2)
    base = f"/bids/{a.bid_id}/dce"
    assert b.client.get(f"{base}/source").status_code == 404
    assert b.client.put(f"{base}/source", json={"url": PLACE}).status_code == 404
    assert b.client.post(f"{base}/retrieve", json={"mode": "anonymous"}).status_code == 404
    assert b.client.get(f"/bids/{uuid.uuid4()}/dce/source").status_code == 404


# ---------- final review: C1, I2, M3, M6, M9 -----------------------------------------------


def test_an_unknown_atexo_host_is_guided(make_client: Any, outbox: Outbox, db: Session) -> None:
    w = World(make_client, outbox, db)
    url = "https://atexo.exemple.fr/entreprise/consultation/1?orgAcronyme=a"
    body = w.client.put(f"/bids/{w.bid_id}/dce/source", json={"url": url}).json()
    assert (body["platform"], body["automatic"]) == ("atexo", False)
    assert len(body["guide"]) == 3
    res = w.client.post(f"/bids/{w.bid_id}/dce/retrieve", json={"mode": "anonymous"})
    assert (res.status_code, res.json()["error"]["code"]) == (422, "not_automatic")


def test_an_http_link_to_place_is_upgraded(make_client: Any, outbox: Outbox, db: Session) -> None:
    w = World(make_client, outbox, db)
    url = "http://www.marches-publics.gouv.fr/entreprise/consultation/7?orgAcronyme=a"
    body = w.client.put(f"/bids/{w.bid_id}/dce/source", json={"url": url}).json()
    assert body["url"].startswith("https://") and body["automatic"] is True


def test_a_link_with_a_nul_is_refused(make_client: Any, outbox: Outbox, db: Session) -> None:
    w = World(make_client, outbox, db)
    res = w.client.put(
        f"/bids/{w.bid_id}/dce/source", json={"url": "https://www.marches-publics.gouv.fr/a\u0000"}
    )
    assert (res.status_code, res.json()["error"]["code"]) == (422, "bad_link")


def test_a_new_link_forgets_the_old_failure(
    make_client: Any, outbox: Outbox, db: Session, queue: FakeQueue
) -> None:
    from app.integrations.atexo import RobotError

    w = World(make_client, outbox, db)
    w.client.post(f"/bids/{w.bid_id}/dce/retrieve", json={"mode": "anonymous"})
    queue.drain_fetches(FakeRobot(RobotError("closed")))
    source = w.client.get(f"/bids/{w.bid_id}/dce/source").json()
    assert source["last_fetch"]["outcome"] == "closed"
    other = "https://www.marches-publics.gouv.fr/entreprise/consultation/42?orgAcronyme=a"
    source = w.client.put(f"/bids/{w.bid_id}/dce/source", json={"url": other}).json()
    assert source["last_fetch"] is None  # the robot can be tried on the new link


def test_identified_mode_needs_a_contact(make_client: Any, outbox: Outbox, db: Session) -> None:
    w = World(make_client, outbox, db)
    res = w.client.put("/profile/dce-retrieval", json={"mode": "identified", "contact": {}})
    assert (res.status_code, res.json()["error"]["code"]) == (422, "contact_incomplete")
