"""The DCE e-mail address (24/11): a company forwards the platform's e-mail, or registers its
Pilao address on the platform; the pieces reach the right dossier, or wait « À classer »."""

import uuid
from email.message import EmailMessage
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Connection, select
from sqlalchemy.orm import Session

from app.db.models import File, InboundMail, Organization, User
from app.services import inbound_mail as svc
from tests.api.helpers import signed_in_client
from tests.api.test_bids import CCTP_V1, EICAR, RC, Factory, new_bid, processed
from tests.conftest import FakeQueue, FakeScanner, MemoryStorage, Outbox, _new_session


def mail(to: str, subject: str = "TR: DCE 26SERV02", **kw: Any) -> EmailMessage:
    m = EmailMessage()
    m["From"] = kw.get("sender", "Plateforme <noreply@marches.example>")
    m["To"] = to
    m["Subject"] = subject
    m["Message-ID"] = kw.get("message_id", f"<{uuid.uuid4()}@marches.example>")
    if "auth" in kw:
        m["Authentication-Results"] = kw["auth"]
    m.set_content(str(kw.get("text", "Bonjour, voici le DCE.")))
    for name, data in kw.get("files", [("RC.pdf", RC)]):
        m.add_attachment(data, maintype="application", subtype="octet-stream", filename=name)
    return m


class Mailbox:
    """The worker's side: one e-mail read from the mailbox, in its own session."""

    def __init__(
        self, conn: Connection, storage: MemoryStorage, scanner: FakeScanner, queue: FakeQueue
    ) -> None:
        self.conn, self.storage, self.scanner, self.queue = conn, storage, scanner, queue

    def deliver(self, m: EmailMessage) -> InboundMail | None:
        with _new_session(self.conn) as db:
            return svc.receive(db, m.as_bytes(), self.storage, self.scanner, self.queue)


def setup(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
    n: int = 1,
) -> tuple[TestClient, str, Mailbox]:
    c = signed_in_client(make_client, outbox, n)
    res = c.get("/dce-mail")
    assert res.status_code == 200, res.text
    address = res.json()["address"]
    assert address.startswith("dce+") and address.endswith("@pilao.pro")
    return c, address, Mailbox(conn, storage, scanner, queue)


def test_the_address_is_given_once_and_kept(
    make_client: Factory, outbox: Outbox, conn: Connection
) -> None:
    c = signed_in_client(make_client, outbox)
    first = c.get("/dce-mail").json()
    assert first["address"] == c.get("/dce-mail").json()["address"]
    assert first["active"] is False  # the mailbox is not switched on in the administration
    other = signed_in_client(make_client, outbox, 2)
    assert other.get("/dce-mail").json()["address"] != first["address"]


def test_pieces_go_to_the_dossier_named_in_the_subject(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    bid = new_bid(c, reference="26SERV02")
    new_bid(c, title="Vitrerie des gymnases")
    got = box.deliver(mail(address, files=[("RC.pdf", RC), ("CCTP.pdf", CCTP_V1)]))
    assert got is not None and got.status == "filed" and str(got.bid_id) == bid
    queue.drain_dce()
    versions = c.get(f"/bids/{bid}/dce").json()
    assert [v["version"] for v in versions] == [1]
    v = c.get(f"/bids/{bid}/dce/1").json()
    assert v["status"] == "ready" and sorted(f["path"] for f in v["files"]) == [
        "CCTP.pdf",
        "RC.pdf",
    ]
    assert queue.pending_analyses == []  # the analysis waits for « Lancer l'analyse »
    assert c.get("/dce-mail/inbox").json() == []


def test_a_dossier_that_has_its_dce_asks_what_the_pieces_are(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    bid = new_bid(c, reference="26SERV02")
    processed(c, queue, bid, ("RC.pdf", RC))
    box.deliver(mail(address, files=[("CCTP.pdf", CCTP_V1)]))
    inbox = c.get("/dce-mail/inbox").json()
    assert len(inbox) == 1
    item = inbox[0]
    assert item["suggested_bid"]["id"] == bid
    assert item["attachments"] == ["CCTP.pdf"] and item["kind"] == "dce"
    res = c.post(f"/dce-mail/inbox/{item['id']}/file", json={"bid_id": bid, "mode": "add"})
    assert res.status_code == 202, res.text
    assert res.json() == {"bid_id": bid, "version": 1}
    queue.drain_dce()
    v = c.get(f"/bids/{bid}/dce/1").json()
    assert sorted(f["path"] for f in v["files"]) == ["CCTP.pdf", "RC.pdf"]
    assert c.get("/dce-mail/inbox").json() == []


def test_a_new_version_can_be_chosen(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    bid = new_bid(c, reference="26SERV02")
    processed(c, queue, bid, ("RC.pdf", RC))
    box.deliver(mail(address, files=[("CCTP.pdf", CCTP_V1)]))
    item = c.get("/dce-mail/inbox").json()[0]
    res = c.post(f"/dce-mail/inbox/{item['id']}/file", json={"bid_id": bid, "mode": "new"})
    assert res.status_code == 202 and res.json()["version"] == 2
    assert c.post(f"/dce-mail/inbox/{item['id']}/file", json={"bid_id": bid}).status_code == 404


def test_an_email_for_no_dossier_waits_and_can_open_one(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    box.deliver(mail(address, subject="TR: Mise à disposition du DCE - Nettoyage de la piscine"))
    item = c.get("/dce-mail/inbox").json()[0]
    assert item["suggested_bid"] is None
    assert item["subject"] == "TR: Mise à disposition du DCE - Nettoyage de la piscine"
    res = c.post(f"/dce-mail/inbox/{item['id']}/new-bid")
    assert res.status_code == 201, res.text
    bid = res.json()["bid_id"]
    assert c.get(f"/bids/{bid}").json()["title"] == "Nettoyage de la piscine"
    queue.drain_dce()
    assert c.get(f"/bids/{bid}/dce/1").json()["status"] == "ready"
    assert queue.pending_analyses == []


def test_ignoring_an_email_removes_its_pieces(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    box.deliver(mail(address, subject="Divers"))
    assert len(storage.objects) == 1
    item = c.get("/dce-mail/inbox").json()[0]
    assert c.delete(f"/dce-mail/inbox/{item['id']}").status_code == 204
    assert storage.objects == {}
    assert c.get("/dce-mail/inbox").json() == []


def test_the_same_email_is_received_once(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    m = mail(address, subject="Divers", message_id="<once@x.fr>")
    box.deliver(m)
    box.deliver(m)
    assert len(c.get("/dce-mail/inbox").json()) == 1
    assert len(storage.objects) == 1


def test_unreadable_and_infected_pieces_are_listed_not_kept(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    files = [
        ("RC.pdf", RC),
        ("notes.txt", b"bonjour"),
        ("virus.pdf", EICAR),
        ("logo.gif", b"GIF89a"),
    ]
    box.deliver(mail(address, subject="Divers", files=files))
    item = c.get("/dce-mail/inbox").json()[0]
    assert item["attachments"] == ["RC.pdf"]
    reasons = {s["path"]: s["reason"] for s in item["skipped"]}
    assert reasons["virus.pdf"] == "virus détecté"
    assert reasons["notes.txt"] == reasons["logo.gif"] == "format non lu par Pilao"


def test_nothing_usable_is_not_kept(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    got = box.deliver(mail(address, subject="Bonjour", text="Merci.", files=[]))
    assert got is not None and got.status == "ignored"
    assert c.get("/dce-mail/inbox").json() == []


def test_a_notice_that_the_dce_changed_shows_on_the_dossier(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    bid = new_bid(c, reference="26SERV02")
    link = "https://www.marches-publics.gouv.fr/entreprise/consultation/1?orgAcronyme=a1b"
    box.deliver(
        mail(
            address,
            subject="Avis de modification - consultation 26SERV02",
            text=f"Le DCE a été modifié : {link}",
            files=[],
        )
    )
    notices = c.get(f"/bids/{bid}/dce-notices").json()
    assert len(notices) == 1 and notices[0]["links"] == [link]
    assert c.get("/dce-mail/inbox").json() == []
    assert c.delete(f"/dce-mail/notices/{notices[0]['id']}").status_code == 204
    assert c.get(f"/bids/{bid}/dce-notices").json() == []


def test_a_link_for_no_dossier_waits_to_be_sorted(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    link = "https://www.marches-publics.info/dce/telecharger?id=42"
    box.deliver(mail(address, subject="Votre DCE", text=f"Téléchargez le DCE : {link}", files=[]))
    item = c.get("/dce-mail/inbox").json()[0]
    assert item["kind"] == "notice" and item["links"] == [link] and item["attachments"] == []


def test_an_unknown_address_or_a_stranger_is_dropped(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    _, _, box = setup(make_client, outbox, conn, storage, scanner, queue)
    assert box.deliver(mail("dce+zzzzzz@pilao.pro")) is None
    assert box.deliver(mail("dce@pilao.pro", sender="inconnu@ailleurs.fr")) is None
    # one of the company's users, but the server did not check the sender: dropped
    assert box.deliver(mail("dce@pilao.pro", sender="user1@example.fr")) is None
    assert storage.objects == {}


def test_a_checked_user_of_the_company_can_write_to_the_plain_address(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, _, box = setup(make_client, outbox, conn, storage, scanner, queue)
    bid = new_bid(c, reference="26SERV02")
    got = box.deliver(
        mail(
            "dce@pilao.pro",
            sender="User 1 <user1@example.fr>",
            auth="mx; dmarc=pass header.from=example.fr",
        )
    )
    # never filed by itself on the sender alone: it waits « À classer », with its suggestion
    assert got is not None and got.status == "to_sort"
    item = c.get("/dce-mail/inbox").json()[0]
    assert item["suggested_bid"]["id"] == bid and item["sender"] == "user1@example.fr"


def test_a_company_sees_and_sorts_only_its_own_emails(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    a, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    box.deliver(mail(address, subject="Divers"))
    item = a.get("/dce-mail/inbox").json()[0]
    b = signed_in_client(make_client, outbox, 2)
    other_bid = new_bid(b)
    assert b.get("/dce-mail/inbox").json() == []
    assert b.delete(f"/dce-mail/inbox/{item['id']}").status_code == 404
    res = b.post(f"/dce-mail/inbox/{item['id']}/file", json={"bid_id": other_bid, "mode": "new"})
    assert res.status_code == 404
    # nor into another company's dossier
    res = a.post(f"/dce-mail/inbox/{item['id']}/file", json={"bid_id": other_bid, "mode": "new"})
    assert res.status_code == 404


def test_the_owner_is_the_author_when_the_sender_is_not_a_user(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    new_bid(c, reference="26SERV02")
    got = box.deliver(mail(address))
    assert got is not None
    with _new_session(conn) as db:
        user = db.scalars(select(User).where(User.email == "user1@example.fr")).one()
        from app.db.models import DceVersion

        version = db.scalars(select(DceVersion)).one()
        assert version.uploaded_by == user.id
        assert db.scalars(select(File).where(File.id.in_(version.source_file_ids))).all()
        org = db.get_one(Organization, user.org_id)
        assert org.dce_mail_code and org.dce_mail_code in address


def test_the_address_is_active_once_the_mailbox_is_set(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    from app.core import crypto
    from tests.core.test_runtime import put

    c = signed_in_client(make_client, outbox)
    put(db, "dce_mail.enabled", True)
    db.commit()
    assert c.get("/dce-mail").json()["active"] is False  # no password yet
    put(db, "dce_mail.password", secret=crypto.encrypt("secret", "dce_mail.password"))
    db.commit()
    assert c.get("/dce-mail").json()["active"] is True


def test_the_routes_need_the_response_module(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    c = signed_in_client(make_client, outbox)
    org = db.scalars(select(Organization)).one()
    org.modules = ["veille"]
    db.commit()
    assert c.get("/dce-mail").status_code == 403
    assert c.get("/dce-mail/inbox").status_code == 403


def test_what_is_left_to_sort_too_long_is_removed(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    from datetime import UTC, datetime, timedelta

    c, address, box = setup(make_client, outbox, conn, storage, scanner, queue)
    box.deliver(mail(address, subject="Divers"))
    box.deliver(mail(address, subject="Hier"))
    with _new_session(conn) as db:
        old = db.scalars(select(InboundMail).where(InboundMail.subject == "Divers")).one()
        old.received_at = datetime.now(UTC) - timedelta(days=31)
        db.commit()
        assert svc.purge(db, storage) == 1
    assert [m["subject"] for m in c.get("/dce-mail/inbox").json()] == ["Hier"]
    assert len(storage.objects) == 1
    with _new_session(conn) as db:
        assert svc.purge(db, storage, datetime.now(UTC) + timedelta(days=200)) == 1
        assert db.scalars(select(InboundMail)).all() == []
