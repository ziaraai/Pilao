"""The DCE mailbox read every 2 minutes (ADR-055): each e-mail read once, then deleted."""

from email.message import EmailMessage

from sqlalchemy import Connection

from app.integrations.imap_mailbox import MailboxError, Waiting
from app.services import inbound_mail as svc
from tests.api.test_bids import Factory, new_bid
from tests.api.test_dce_mail import mail, setup
from tests.conftest import FakeQueue, FakeScanner, MemoryStorage, Outbox, _new_session


class FakeMailbox:
    def __init__(self, messages: dict[str, EmailMessage], sizes: dict[str, int] | None = None):
        self.raw = {uid: m.as_bytes() for uid, m in messages.items()}
        self.sizes = sizes or {}
        self.flagged: set[str] = set()
        self.deleted: list[str] = []
        self.broken: set[str] = set()
        self.headers_only: list[str] = []

    def waiting(self) -> list[Waiting]:
        return [
            Waiting(uid, self.sizes.get(uid, len(raw)), uid in self.flagged)
            for uid, raw in self.raw.items()
            if uid not in self.deleted
        ]

    def fetch(self, uid: str) -> bytes:
        if uid in self.broken:
            raise RuntimeError("unreadable")
        return self.raw[uid]

    def fetch_header(self, uid: str) -> bytes:
        self.headers_only.append(uid)
        return self.raw[uid].split(b"\n\n", 1)[0] + b"\n\n"

    def flag(self, uid: str) -> None:
        self.flagged.add(uid)

    def delete(self, uid: str) -> None:
        self.deleted.append(uid)

    def close(self) -> None:
        pass


def run(
    conn: Connection,
    box: FakeMailbox,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> svc.PollResult:
    return svc.poll(lambda: _new_session(conn), box, storage, scanner, queue)


def test_each_email_is_read_then_deleted(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, _ = setup(make_client, outbox, conn, storage, scanner, queue)
    bid = new_bid(c, reference="26SERV02")
    box = FakeMailbox({"1": mail(address), "2": mail("dce+zzzzzz@pilao.pro")})
    result = run(conn, box, storage, scanner, queue)
    assert (result.read, result.kept, result.dropped, result.failed) == (2, 1, 1, 0)
    assert box.deleted == ["1", "2"]
    queue.drain_dce()
    assert c.get(f"/bids/{bid}/dce/1").json()["status"] == "ready"
    assert run(conn, box, storage, scanner, queue).read == 0  # nothing left


def test_the_antivirus_down_stops_the_pass_and_keeps_the_emails(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    _, address, _ = setup(make_client, outbox, conn, storage, scanner, queue)
    box = FakeMailbox({"1": mail(address), "2": mail(address)})
    scanner.down = True
    result = run(conn, box, storage, scanner, queue)
    assert result.stopped == "antivirus indisponible"
    assert box.deleted == [] and box.flagged == set() and storage.objects == {}
    scanner.down = False
    assert run(conn, box, storage, scanner, queue).kept == 2  # read again next time


def test_an_email_that_cannot_be_read_is_flagged_and_left(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    _, address, _ = setup(make_client, outbox, conn, storage, scanner, queue)
    box = FakeMailbox({"1": mail(address, subject="A"), "2": mail(address, subject="B")})
    box.broken.add("1")
    result = run(conn, box, storage, scanner, queue)
    assert (result.failed, result.kept) == (1, 1)
    assert box.flagged == {"1"} and box.deleted == ["2"]
    assert run(conn, box, storage, scanner, queue).read == 0  # never read again by itself


def test_a_mailbox_that_breaks_stops_the_pass(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    _, address, _ = setup(make_client, outbox, conn, storage, scanner, queue)
    box = FakeMailbox({"1": mail(address)})

    def down(uid: str) -> bytes:
        raise MailboxError("Serveur de messagerie injoignable.")

    box.fetch = down  # type: ignore[method-assign]
    result = run(conn, box, storage, scanner, queue)
    assert result.stopped == "Serveur de messagerie injoignable."
    assert box.deleted == [] and box.flagged == set()


def test_a_too_big_email_is_announced_not_read(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
) -> None:
    c, address, _ = setup(make_client, outbox, conn, storage, scanner, queue)
    box = FakeMailbox({"1": mail(address, subject="DCE complet")}, sizes={"1": 200 * 2**20})
    run(conn, box, storage, scanner, queue)
    assert box.headers_only == ["1"] and box.deleted == ["1"] and storage.objects == {}
    item = c.get("/dce-mail/inbox").json()[0]
    assert item["subject"] == "DCE complet" and item["attachments"] == []
    assert item["note"] == "message trop volumineux (plus de 60 Mo)"


def test_two_passes_never_run_together(
    make_client: Factory,
    outbox: Outbox,
    conn: Connection,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
    engine: object,
) -> None:
    from sqlalchemy import Engine, text

    assert isinstance(engine, Engine)
    with engine.connect() as other:
        other.execute(text("select pg_advisory_lock(:k)"), {"k": svc.POLL_LOCK})
        try:
            result = run(conn, FakeMailbox({}), storage, scanner, queue)
            assert result.stopped == "relève déjà en cours"
        finally:
            other.execute(text("select pg_advisory_unlock(:k)"), {"k": svc.POLL_LOCK})
