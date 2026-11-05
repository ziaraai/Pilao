"""`python -m app.cli load-tenders`: the normalized notices path, end to end."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection

from app import cli
from tests.api.helpers import signed_in_client
from tests.conftest import FakeQueue, Outbox, _new_session


def test_load_tenders_matches_them_for_every_company(
    make_client: Callable[[], TestClient],
    outbox: Outbox,
    queue: FakeQueue,
    conn: Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    c = signed_in_client(make_client, outbox)
    c.put("/profile", json={"cpv_codes": ["90910000"], "departments": ["69"]})
    queue.drain_tenders()
    deadline = (datetime.now(UTC) + timedelta(days=20)).isoformat()
    path = tmp_path / "annonces.json"
    path.write_text(
        json.dumps(
            [
                {
                    "source": "boamp",
                    "source_id": "26-1",
                    "title": "Nettoyage des écoles",
                    "cpv_codes": ["90911200"],
                    "departments": ["69"],
                    "deadline_at": deadline,
                },
                {
                    "source": "boamp",
                    "source_id": "26-2",
                    "title": "Voirie",
                    "cpv_codes": ["45233140"],
                    "departments": ["69"],
                    "deadline_at": deadline,
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: lambda: _new_session(conn))
    monkeypatch.setattr(cli, "get_job_queue", lambda: queue)
    monkeypatch.setattr(cli, "get_mailer", lambda: outbox)
    assert cli.main(["load-tenders", str(path)]) == 0
    assert "2 créée(s)" in capsys.readouterr().out
    queue.drain_tenders()
    assert [t["title"] for t in c.get("/tenders").json()["items"]] == ["Nettoyage des écoles"]
