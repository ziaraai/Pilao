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


def test_receive_dce_mail_reads_a_file_or_the_standard_input(
    make_client: Callable[[], TestClient],
    outbox: Outbox,
    queue: FakeQueue,
    conn: Connection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ADR-055: an e-mail replayed by hand, as the DCE mailbox would hand it over."""
    import io
    import sys

    from app.storage import antivirus, objects
    from tests.api.test_dce_mail import mail
    from tests.conftest import FakeScanner, MemoryStorage

    c = signed_in_client(make_client, outbox)
    address = c.get("/dce-mail").json()["address"]
    monkeypatch.setattr(cli, "get_sessionmaker", lambda: lambda: _new_session(conn))
    monkeypatch.setattr(cli, "get_job_queue", lambda: queue)
    monkeypatch.setattr(objects, "get_storage", lambda: MemoryStorage())
    monkeypatch.setattr(antivirus, "get_scanner", lambda: FakeScanner())
    path = tmp_path / "message.eml"
    path.write_bytes(mail(address, subject="Divers").as_bytes())
    assert cli.main(["receive-dce-mail", str(path)]) == 0
    assert "message.eml : to_sort, 1 pièce(s)" in capsys.readouterr().out
    raw = mail(address, subject="Autre").as_bytes()
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw)))
    assert cli.main(["receive-dce-mail", "-"]) == 0
    assert "- : to_sort" in capsys.readouterr().out
    assert len(c.get("/dce-mail/inbox").json()) == 2
    path.write_bytes(mail("dce+zzzzzz@pilao.pro").as_bytes())
    cli.main(["receive-dce-mail", str(path)])
    assert "pour personne" in capsys.readouterr().out
