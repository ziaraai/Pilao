import os
import uuid
from collections.abc import Callable, Iterator

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://pilao:pilao@localhost:5432/pilao_test")

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.orm import Session

from alembic import command
from app.core.email import Email


def alembic_config(engine: Engine) -> Config:
    cfg = Config("alembic.ini")
    cfg.attributes["engine"] = engine
    return cfg


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = os.environ["DATABASE_URL"]
    # The fixture drops the whole schema: never let it run against a real database.
    assert url.rsplit("/", 1)[-1].endswith("_test"), "tests need a *_test database"
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    command.upgrade(alembic_config(eng), "head")
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine: Engine) -> Iterator[Connection]:
    """One connection inside an outer transaction that is always rolled back."""
    connection = engine.connect()
    trans = connection.begin()
    yield connection
    trans.rollback()
    connection.close()


@pytest.fixture(autouse=True)
def credits_aplenty(request: pytest.FixtureRequest) -> None:
    """Lot 4: the tests of the paid actions written before the credits do not count them; the
    test modules that check the credits themselves declare ``REAL_CREDITS = True``."""
    if getattr(request.module, "REAL_CREDITS", False):
        return
    if not {"conn", "db", "make_client"} & set(request.fixturenames):
        return
    request.getfixturevalue("conn").execute(text("UPDATE plans SET monthly_credits = 100000"))


def _new_session(conn: Connection) -> Session:
    return Session(conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def db(conn: Connection) -> Iterator[Session]:
    session = _new_session(conn)
    yield session
    session.close()


class Outbox:
    def __init__(self) -> None:
        self.sent: list[Email] = []

    def send(self, message: Email) -> None:
        self.sent.append(message)

    def last_token(self) -> str:
        return self.sent[-1].body.split("token=")[1].split()[0]


class MemoryStorage:
    """In-memory ObjectStorage for API tests (S3 itself is covered with moto)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_put = False

    def put(self, key: str, fileobj, content_type: str) -> None:  # type: ignore[no-untyped-def]
        if self.fail_put:
            raise RuntimeError("storage down")
        fileobj.seek(0)
        self.objects[key] = fileobj.read()
        fileobj.seek(0)

    def get(self, key: str):  # type: ignore[no-untyped-def]
        import io

        return io.BytesIO(self.objects[key])

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def signed_download_url(self, key: str, filename: str, ttl_seconds: int) -> str:
        return f"https://storage.test/{key}?name={filename}&expires={ttl_seconds}&sig=abc"


class FakeScanner:
    """Flags any content containing the EICAR marker; can simulate an outage."""

    def __init__(self) -> None:
        self.down = False
        self.too_large = False

    def scan(self, fileobj) -> str | None:  # type: ignore[no-untyped-def]
        from app.storage.antivirus import ScannerUnavailable, ScanTooLarge

        if self.down:
            raise ScannerUnavailable("down")
        if self.too_large:
            raise ScanTooLarge("INSTREAM size limit exceeded")
        fileobj.seek(0)
        found = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in fileobj.read()
        fileobj.seek(0)
        return "Eicar-Test-Signature" if found else None


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture
def scanner() -> FakeScanner:
    return FakeScanner()


class CountingEmbedder:
    """HashEmbedder that records every batch and can be told to fail or return bad shapes."""

    def __init__(self) -> None:
        from app.ai.embeddings import HashEmbedder
        from app.core.config import get_settings

        self._inner = HashEmbedder(get_settings().embedding_dim)
        self.batches: list[list[str]] = []
        self.fail_times = 0
        self.bad_dim = False

    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def texts_embedded(self) -> int:
        return sum(len(b) for b in self.batches)

    def embed(self, texts: list[str]):  # type: ignore[no-untyped-def]
        from app.ai.embeddings import EmbeddingError, EmbeddingResult

        if self.fail_times > 0:
            self.fail_times -= 1
            raise EmbeddingError("provider down")
        self.batches.append(list(texts))
        result = self._inner.embed(texts)
        if self.bad_dim:
            return EmbeddingResult([v[:10] for v in result.vectors], "bad", 0, 0.0)
        return result


class FakeQueue:
    """Collects enqueued documents; ``drain`` plays the worker on the test connection."""

    def __init__(
        self,
        conn: Connection,
        storage: MemoryStorage,
        embedder: CountingEmbedder,
        scanner: "FakeScanner",
    ) -> None:
        self._conn, self._storage, self._embedder = conn, storage, embedder
        self._scanner = scanner
        self.pending: list[uuid.UUID] = []
        self.pending_reads: list[uuid.UUID] = []
        self.pending_dce: list[uuid.UUID] = []
        self.pending_analyses: list[uuid.UUID] = []
        self.pending_sections: list[uuid.UUID] = []
        self.pending_conformity: list[uuid.UUID] = []
        self.pending_exports: list[uuid.UUID] = []
        self.pending_match: list[list[uuid.UUID]] = []
        self.pending_rematch: list[uuid.UUID] = []
        self.pending_score: list[uuid.UUID] = []
        self.pending_org_exports: list[uuid.UUID] = []
        self.pending_prefill: list[uuid.UUID] = []
        self.ocr = None  # set to an OCR engine to exercise scanned pages
        self.down = False

    def enqueue_index_document(self, doc_id: uuid.UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.pending.append(doc_id)

    def enqueue_read_compliance_document(self, doc_id: uuid.UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.pending_reads.append(doc_id)

    def drain_reads(self, reader) -> None:  # type: ignore[no-untyped-def]
        from app.services.vault import run_read_document

        while self.pending_reads:
            doc_id = self.pending_reads.pop(0)
            with _new_session(self._conn) as session:
                run_read_document(session, doc_id, self._storage, reader)

    def enqueue_process_dce(self, version_id: uuid.UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.pending_dce.append(version_id)

    def drain_dce(self) -> None:
        from app.services.dce import run_process_dce

        while self.pending_dce:
            version_id = self.pending_dce.pop(0)
            with _new_session(self._conn) as session:
                run_process_dce(
                    session, version_id, self._storage, self._scanner, self.ocr, queue=self
                )

    def enqueue_analyze_dce(self, analysis_id: uuid.UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.pending_analyses.append(analysis_id)

    def drain_analyses(self) -> None:
        from app.services.dce_analysis import run_analyze_dce

        while self.pending_analyses:
            analysis_id = self.pending_analyses.pop(0)
            with _new_session(self._conn) as session:
                run_analyze_dce(session, analysis_id)

    def enqueue_draft_section(self, section_id: uuid.UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.pending_sections.append(section_id)

    def enqueue_conformity(self, memoir_id: uuid.UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.pending_conformity.append(memoir_id)

    def drain_memoir(self) -> None:
        """Every chapter job, then the conformity matrix they trigger (as RQ would)."""
        from app.services.memoir_drafting import run_conformity, run_draft_section

        while self.pending_sections or self.pending_conformity:
            if self.pending_sections:
                section_id = self.pending_sections.pop(0)
                with _new_session(self._conn) as session:
                    run_draft_section(session, section_id, self._embedder, self)
            else:
                memoir_id = self.pending_conformity.pop(0)
                with _new_session(self._conn) as session:
                    run_conformity(session, memoir_id)

    def enqueue_export(self, document_id: uuid.UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.pending_exports.append(document_id)

    def drain_exports(self, converter) -> None:  # type: ignore[no-untyped-def]
        from app.services.exports import run_export

        while self.pending_exports:
            document_id = self.pending_exports.pop(0)
            with _new_session(self._conn) as session:
                run_export(session, document_id, self._storage, converter)

    def enqueue_match_tenders(self, tender_ids: list[uuid.UUID]) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.pending_match.append(list(tender_ids))

    def enqueue_rematch_org(self, org_id: uuid.UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.pending_rematch.append(org_id)

    def enqueue_score_tenders(self, org_id: uuid.UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        if org_id not in self.pending_score:  # several queued jobs would score nothing more
            self.pending_score.append(org_id)

    def drain_tenders(self) -> None:
        """Matching (unscoped), profile re-matching, then scoring, as the worker would."""
        from app.services.tenders import match_tenders, rematch_org, score_org

        while self.pending_match or self.pending_rematch or self.pending_score:
            if self.pending_match:
                ids = self.pending_match.pop(0)
                with _new_session(self._conn) as session:
                    match_tenders(session, ids, self)
            elif self.pending_rematch:
                org_id = self.pending_rematch.pop(0)
                with _new_session(self._conn) as session:
                    rematch_org(session, org_id, self)
            else:
                org_id = self.pending_score.pop(0)
                with _new_session(self._conn) as session:
                    score_org(session, org_id, self)

    def enqueue_org_export(self, request_id: uuid.UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.pending_org_exports.append(request_id)

    def drain_org_exports(self) -> None:
        from app.services.org_data import run_org_export

        while self.pending_org_exports:
            request_id = self.pending_org_exports.pop(0)
            with _new_session(self._conn) as session:
                run_org_export(session, request_id, self._storage)

    def enqueue_profile_prefill(self, org_id: uuid.UUID) -> None:
        if self.down:
            raise ConnectionError("redis down")
        self.pending_prefill.append(org_id)

    def drain_profile_prefill(self) -> None:
        from app.services.profile_prefill import run_profile_prefill

        while self.pending_prefill:
            org_id = self.pending_prefill.pop(0)
            with _new_session(self._conn) as session:
                run_profile_prefill(session, org_id, self._storage)

    def drain(self) -> None:
        from app.services.knowledge import run_index_document

        while self.pending:
            doc_id = self.pending.pop(0)
            with _new_session(self._conn) as session:
                run_index_document(session, doc_id, self._storage, self._embedder)


@pytest.fixture
def embedder() -> CountingEmbedder:
    return CountingEmbedder()


@pytest.fixture
def queue(
    conn: Connection, storage: MemoryStorage, embedder: CountingEmbedder, scanner: FakeScanner
) -> FakeQueue:
    return FakeQueue(conn, storage, embedder, scanner)


class FakeReader:
    """Stands in for the vision model: returns ``result`` or raises ``error``."""

    def __init__(self) -> None:
        self.result = None
        self.error: Exception | None = None
        self.calls = 0

    def read(self, db, org, fileobj, mime):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def reader() -> FakeReader:
    return FakeReader()


class NoDirectory:
    """Default registry stub: knows no company."""

    def lookup_siret(self, siret: str) -> None:
        return None


@pytest.fixture
def outbox() -> Outbox:
    return Outbox()


@pytest.fixture
def make_client(
    conn: Connection,
    outbox: Outbox,
    storage: MemoryStorage,
    scanner: FakeScanner,
    queue: FakeQueue,
    embedder: CountingEmbedder,
) -> Iterator[Callable[[], TestClient]]:
    """Factory of independent HTTP clients (own cookie jar), one DB session per request."""
    from app.ai.embeddings import get_embedder
    from app.core.email import get_mailer
    from app.db.session import get_db
    from app.integrations.recherche_entreprises import get_company_directory
    from app.main import app
    from app.routers.files import _scanner
    from app.storage.objects import get_storage
    from app.workers.queue import get_job_queue

    def override_db() -> Iterator[Session]:
        with _new_session(conn) as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_mailer] = lambda: outbox
    app.dependency_overrides[get_company_directory] = lambda: NoDirectory()  # never hit the network
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[_scanner] = lambda: scanner
    app.dependency_overrides[get_job_queue] = lambda: queue
    app.dependency_overrides[get_embedder] = lambda: embedder
    yield lambda: TestClient(app, headers={"Origin": "http://localhost:3000"})
    app.dependency_overrides.clear()
