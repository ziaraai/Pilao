"""Feedback from inside the application, and the time saved on bids (P4-02)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, select
from sqlalchemy.orm import Session

from app import cli
from app.core.config import get_settings
from app.db.models import Feedback
from tests.api.helpers import signed_in_client
from tests.conftest import Outbox, _new_session

Factory = Callable[[], TestClient]


def test_feedback_is_kept_with_the_company_and_mailed_to_the_team(
    make_client: Factory, outbox: Outbox, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "feedback_email", "equipe@pilao.example")
    c = signed_in_client(make_client, outbox, 1)
    other = signed_in_client(make_client, outbox, 2)
    bid = c.post("/bids", json={"title": "Médiathèque"}).json()
    foreign = other.post("/bids", json={"title": "Secret de B"}).json()
    body = {
        "kind": "problem",
        "message": "  L'export PDF a mis longtemps.  ",
        "page": f"/dossiers/{bid['id']}",
        "bid_id": bid["id"],
    }
    res = c.post("/feedback", json=body)
    assert res.status_code == 201 and res.json()["kind"] == "problem"
    [mail] = outbox.sent[-1:]
    assert mail.to == "equipe@pilao.example"
    assert mail.subject == "[Pilao] Problème — Entreprise 1"
    assert "User 1 (user1@example.fr), Entreprise 1" in mail.body
    assert f"Page : /dossiers/{bid['id']}" in mail.body and "Dossier : Médiathèque" in mail.body
    assert mail.body.endswith("L'export PDF a mis longtemps.\n")

    # another company's bid is not found, so not linked (and its title never mailed)
    res = c.post("/feedback", json={**body, "kind": "idea", "bid_id": foreign["id"]})
    assert res.status_code == 201 and "Secret de B" not in outbox.sent[-1].body
    rows = db.scalars(select(Feedback).order_by(Feedback.created_at)).all()
    assert [(r.kind, str(r.bid_id) if r.bid_id else None) for r in rows] == [
        ("problem", bid["id"]),
        ("idea", None),
    ]
    assert rows[0].message == "L'export PDF a mis longtemps."

    monkeypatch.setattr(get_settings(), "feedback_email", "")
    sent = len(outbox.sent)
    assert c.post("/feedback", json={"kind": "question", "message": "?"}).status_code == 201
    assert len(outbox.sent) == sent  # no inbox configured: stored only, the report lists it

    assert c.post("/feedback", json={"kind": "question", "message": ""}).status_code == 422
    assert c.post("/feedback", json={"kind": "spam", "message": "x"}).status_code == 422
    monkeypatch.setattr(get_settings(), "feedback_max_per_hour", 3)
    capped = c.post("/feedback", json={"kind": "idea", "message": "encore"})
    assert capped.status_code == 429 and capped.json()["error"]["code"] == "too_many_feedback"
    assert make_client().post("/feedback", json={"kind": "idea", "message": "x"}).status_code == 401


def test_time_saved_is_summed_on_the_dashboard(make_client: Factory, outbox: Outbox) -> None:
    c = signed_in_client(make_client, outbox, 1)
    other = signed_in_client(make_client, outbox, 2)
    assert c.get("/dashboard").json()["time_saved"] == {
        "bids": 0,
        "minutes_with_pilao": 0,
        "minutes_usual": 0,
        "minutes_saved": 0,
    }
    times = [(90, 480), (120, 360), (60, None)]  # the last one is only half filled in
    for i, (with_pilao, usual) in enumerate(times):
        bid = c.post("/bids", json={"title": f"Dossier {i}"}).json()
        res = c.patch(
            f"/bids/{bid['id']}",
            json={"minutes_with_pilao": with_pilao, "minutes_usual": usual},
        )
        assert res.status_code == 200 and res.json()["minutes_with_pilao"] == with_pilao
    theirs = other.post("/bids", json={"title": "B"}).json()
    other.patch(f"/bids/{theirs['id']}", json={"minutes_with_pilao": 1, "minutes_usual": 9999})
    assert c.get("/dashboard").json()["time_saved"] == {
        "bids": 2,
        "minutes_with_pilao": 210,
        "minutes_usual": 840,
        "minutes_saved": 630,
    }
    bad = c.patch(f"/bids/{theirs['id']}", json={"minutes_usual": 10})
    assert bad.status_code == 404  # another company's bid
    first = c.get("/bids").json()[0]["id"]
    assert c.patch(f"/bids/{first}", json={"minutes_usual": -5}).status_code == 422


def test_the_team_report_lists_every_company(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    a = signed_in_client(make_client, outbox, 1)
    b = signed_in_client(make_client, outbox, 2)
    a.post("/feedback", json={"kind": "idea", "message": "Un export Excel des références"})
    b.post(
        "/feedback", json={"kind": "problem", "message": "Ligne 1\nLigne 2", "page": "/annonces"}
    )
    bid = a.post("/bids", json={"title": "Écoles"}).json()
    a.patch(f"/bids/{bid['id']}", json={"minutes_with_pilao": 120, "minutes_usual": 480})
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: lambda: _new_session(conn))

    assert cli.main(["feedback-report", "--csv", str(tmp_path / "retours.csv")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("2 avis depuis 30 jours")
    assert "Idée — Entreprise 1 — user1@example.fr" in out
    assert (
        "Problème — Entreprise 2 — user2@example.fr\n  page : /annonces\n  Ligne 1\n  Ligne 2"
        in out
    )
    assert "Entreprise 1 : 1 dossier(s), 6 h gagnées (75 %)" in out
    assert cli._duration(330) == "5 h 30" and cli._duration(45) == "45 min"
    csv = (tmp_path / "retours.csv").read_text(encoding="utf-8-sig").splitlines()
    assert csv[0] == "date;entreprise;utilisateur;type;page;message" and len(csv) >= 3
