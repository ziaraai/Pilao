"""Administration, lot 3: turn a company's modules on or off, the catalogue (spec §3.1, §5.4)."""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Organization
from tests.api.helpers import signed_in_client
from tests.api.test_admin_accounts import admin, journal, org_id_of
from tests.api.test_modules import set_modules
from tests.conftest import FakeQueue, Outbox

Factory = Callable[[], TestClient]


def toggle(client: TestClient, org_id: str, key: str, enabled: bool):  # type: ignore[no-untyped-def]
    return client.put(f"/admin/organizations/{org_id}/modules/{key}", json={"enabled": enabled})


def test_disable_then_enable(make_client: Factory, outbox: Outbox, db: Session) -> None:
    company = signed_in_client(make_client, outbox)
    org_id = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    res = toggle(client, org_id, "reponse", False)
    assert res.status_code == 200, res.text
    assert res.json() == {"modules": ["veille"]}
    assert company.get("/bids").status_code == 403
    [off] = journal(db, "module_disabled")
    assert off.meta == {"module": "reponse", "name": "Réponse aux appels d'offres"}
    assert str(off.org_id) == org_id

    res = toggle(client, org_id, "reponse", True)
    assert res.json() == {"modules": ["veille", "reponse"]}  # the registry's order
    assert company.get("/bids").status_code == 200
    [on] = journal(db, "module_enabled")
    assert on.meta == {"module": "reponse", "name": "Réponse aux appels d'offres"}


def test_same_state_twice_is_harmless(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    org_id = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    assert toggle(client, org_id, "veille", True).json() == {"modules": ["veille", "reponse"]}
    assert toggle(client, org_id, "veille", False).json() == {"modules": ["reponse"]}
    assert toggle(client, org_id, "veille", False).json() == {"modules": ["reponse"]}


def test_enabling_the_watch_catches_up(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    signed_in_client(make_client, outbox)
    org_id = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    toggle(client, org_id, "veille", False)
    toggle(client, org_id, "reponse", False)
    toggle(client, org_id, "reponse", True)
    assert queue.pending_rematch == []  # only the watch triggers a new search
    toggle(client, org_id, "veille", True)
    assert [str(o) for o in queue.pending_rematch] == [org_id]


def test_enabling_works_when_the_queue_is_down(
    make_client: Factory, outbox: Outbox, queue: FakeQueue, db: Session
) -> None:
    signed_in_client(make_client, outbox)
    org_id = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)
    toggle(client, org_id, "veille", False)

    queue.down = True
    res = toggle(client, org_id, "veille", True)
    assert res.status_code == 200
    assert res.json() == {"modules": ["veille", "reponse"]}


def test_unknown_module_and_neighbour(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    neighbour = signed_in_client(make_client, outbox, 2)
    org_id = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    res = toggle(client, org_id, "crm", True)
    assert res.status_code == 404
    assert res.json()["error"] == {"code": "unknown_module", "message": "Module inconnu."}
    assert (
        toggle(client, "00000000-0000-0000-0000-000000000000", "veille", False).status_code == 404
    )

    toggle(client, org_id, "reponse", False)
    assert neighbour.get("/bids").status_code == 200  # another company keeps its modules
    assert neighbour.get("/auth/me").json()["modules"] == ["veille", "reponse"]


def test_catalogue_and_counts(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    signed_in_client(make_client, outbox, 2)
    set_modules(db, "user2@example.fr", ["veille"])
    client, _, _ = admin(make_client, db)

    res = client.get("/admin/modules")
    assert res.status_code == 200, res.text
    veille, reponse = res.json()
    assert (veille["key"], veille["name"]) == ("veille", "Veille des annonces")
    assert (reponse["key"], reponse["name"]) == ("reponse", "Réponse aux appels d'offres")
    assert veille["nav"] == ["Annonces"]
    assert reponse["nav"] == ["Dossiers", "Coffre-fort", "Base documentaire"]
    assert veille["contents"] and reponse["description"]
    assert (veille["organizations"], reponse["organizations"]) == (2, 1)


def test_list_and_detail_show_modules(make_client: Factory, outbox: Outbox, db: Session) -> None:
    signed_in_client(make_client, outbox)
    set_modules(db, "user1@example.fr", ["reponse"])
    org_id = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    [row] = client.get("/admin/organizations").json()
    assert row["modules"] == ["reponse"]
    assert client.get(f"/admin/organizations/{org_id}").json()["modules"] == ["reponse"]


def test_company_session_refused(make_client: Factory, outbox: Outbox, db: Session) -> None:
    company = signed_in_client(make_client, outbox)
    org_id = org_id_of(db, "user1@example.fr")

    assert company.get("/admin/modules").status_code == 401
    assert toggle(company, org_id, "veille", False).status_code == 401
    assert company.get("/auth/me").json()["modules"] == ["veille", "reponse"]


def test_toggle_keeps_keys_it_does_not_know(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    """A key outside the registry (a newer release, a module taken out of the code for a
    while) is ignored, never erased by a toggle."""
    signed_in_client(make_client, outbox)
    set_modules(db, "user1@example.fr", ["veille", "reponse", "crm"])
    org_id = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    assert toggle(client, org_id, "reponse", False).json() == {"modules": ["veille"]}
    db.expire_all()
    assert db.get_one(Organization, uuid.UUID(org_id)).modules == ["veille", "crm"]
    assert toggle(client, org_id, "reponse", True).json() == {"modules": ["veille", "reponse"]}
    db.expire_all()
    assert db.get_one(Organization, uuid.UUID(org_id)).modules == ["veille", "reponse", "crm"]


def test_list_percentage_follows_the_watch(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    """Without « Veille » the profile no longer asks for the watch settings: the companies
    list shows the new percentage at once, not at the next profile save."""
    company = signed_in_client(make_client, outbox)
    assert company.put("/profile", json={"trades": ["vitrerie"]}).status_code == 200
    org_id = org_id_of(db, "user1@example.fr")
    client, _, _ = admin(make_client, db)

    def shown() -> int:
        [row] = client.get("/admin/organizations").json()
        return int(row["completeness_pct"])

    before = shown()
    toggle(client, org_id, "veille", False)
    assert shown() == before + 15 + 10  # CPV/keywords and departments no longer asked
    assert shown() == company.get("/profile/completeness").json()["pct"]
    toggle(client, org_id, "veille", True)
    assert shown() == before
