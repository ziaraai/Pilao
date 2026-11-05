"""Outgoing e-mail (ADR-032): SMTP, the choice of sender, automatic messages that never
stop the hourly run."""

from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any, ClassVar, Self

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import LiteLLMEmbedder
from app.core import email as email_mod
from app.core.config import get_settings
from app.core.email import ConsoleMailer, Email, SmtpMailer, get_mailer, send_quietly
from app.core.errors import ApiError
from app.db.models import Notification, Organization
from app.services.tenders import notify
from tests.api.helpers import signed_in_client
from tests.conftest import Outbox

Factory = Callable[[], TestClient]


class FakeSMTP:
    instances: ClassVar[list["FakeSMTP"]] = []
    fail = False

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host, self.port, self.calls, self.sent = host, port, [], []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> Self:
        if FakeSMTP.fail:
            raise ConnectionRefusedError("smtp down")
        return self

    def __exit__(self, *_: object) -> None:
        self.calls.append("quit")

    def starttls(self, context: Any) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login {user}")

    def send_message(self, msg: Any) -> None:
        self.sent.append(msg)


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[FakeSMTP]]:
    FakeSMTP.instances, FakeSMTP.fail = [], False
    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)
    yield FakeSMTP


def test_smtp_sends_a_plain_french_message(smtp: type[FakeSMTP]) -> None:
    mailer = SmtpMailer(
        "mail.pilao.pro", 587, "Pilao <noreply@pilao.pro>", "noreply@pilao.pro", "x"
    )
    mailer.send(
        Email(to="abdraouf@example.fr", subject="Échéance proche", body="Bonjour, à bientôt.")
    )
    [conn] = smtp.instances
    assert (conn.host, conn.port) == ("mail.pilao.pro", 587)
    assert conn.calls == ["starttls", "login noreply@pilao.pro", "quit"]  # TLS before the password
    [msg] = conn.sent
    assert msg["From"] == "Pilao <noreply@pilao.pro>" and msg["To"] == "abdraouf@example.fr"
    assert msg["Subject"] == "Échéance proche" and msg["Message-ID"].endswith("@pilao.pro>")
    assert msg.get_content().strip() == "Bonjour, à bientôt."

    SmtpMailer("localhost", 25, "noreply@pilao.pro", starttls=False).send(
        Email(to="a@example.fr", subject="s", body="b")
    )
    assert smtp.instances[-1].calls == ["quit"]  # no TLS, no login: a local relay

    import ssl

    local = SmtpMailer("host.docker.internal", 587, "noreply@pilao.pro", verify_tls=False)
    assert local._context.verify_mode == ssl.CERT_NONE and not local._context.check_hostname
    assert mailer._context.verify_mode == ssl.CERT_REQUIRED  # checked unless said otherwise

    smtp.fail = True
    with pytest.raises(ApiError) as err:
        mailer.send(Email(to="a@example.fr", subject="s", body="b"))
    assert err.value.status == 503 and err.value.code == "email_unavailable"


def test_the_sender_follows_the_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    try:
        monkeypatch.setattr(s, "smtp_host", "")
        get_mailer.cache_clear()
        assert isinstance(get_mailer(), ConsoleMailer)
        monkeypatch.setattr(s, "environment", "production")
        get_mailer.cache_clear()
        with pytest.raises(ApiError):  # production without SMTP: nothing goes out
            get_mailer()
        monkeypatch.setattr(s, "smtp_host", "mail.pilao.pro")
        get_mailer.cache_clear()
        assert isinstance(get_mailer(), SmtpMailer)
    finally:
        get_mailer.cache_clear()


class Flaky:
    def __init__(self, down: set[str]) -> None:
        self.down, self.sent = down, []  # type: ignore[var-annotated]

    def send(self, message: Email) -> None:
        if "*" in self.down or message.to in self.down:
            raise ApiError(503, "email_unavailable", "down")
        self.sent.append(message.to)


def test_automatic_messages_never_stop_the_run(
    make_client: Factory, outbox: Outbox, db: Session
) -> None:
    signed_in_client(make_client, outbox, 1)
    org_id = db.scalars(select(Organization.id)).one()
    assert send_quietly(Flaky({"*"}), Email(to="a@example.fr", subject="s", body="b")) is False

    # the mail server is down: nothing recorded, so the alert is tried again next hour
    assert notify(db, Flaky({"*"}), org_id, "expiry", "doc-1", "Sujet", "Corps") is False
    assert db.scalar(select(Notification).where(Notification.key == "doc-1")) is None
    sent = Flaky(set())
    assert notify(db, sent, org_id, "expiry", "doc-1", "Sujet", "Corps") is True
    assert sent.sent == ["user1@example.fr"]
    assert notify(db, sent, org_id, "expiry", "doc-1", "Sujet", "Corps") is False  # once only


def test_embedding_cost_falls_back_to_the_known_price(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    monkeypatch.setattr(get_settings(), "usd_eur_rate", 0.9)
    monkeypatch.setattr(get_settings(), "embedding_price_usd_per_million", 0.1)
    monkeypatch.setattr(
        litellm,
        "embedding",
        lambda **kw: SimpleNamespace(
            data=[{"embedding": [0.0] * 4} for _ in kw["input"]],
            usage=SimpleNamespace(prompt_tokens=500_000),
            _hidden_params={},  # what OpenRouter gives for embeddings: no cost
        ),
    )
    result = LiteLLMEmbedder("openrouter/mistralai/mistral-embed-2312", 4).embed(["a", "b"])
    assert result.cost_eur == pytest.approx(0.5 * 0.1 * 0.9)


def test_the_test_email_command(
    smtp: type[FakeSMTP], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from app import cli

    monkeypatch.setattr(get_settings(), "smtp_host", "host.docker.internal")
    get_mailer.cache_clear()
    try:
        assert cli.main(["send-test-email", "faycal@example.fr"]) == 0
        [msg] = smtp.instances[-1].sent
        assert msg["To"] == "faycal@example.fr" and msg["Subject"] == "Pilao — e-mail de test"
        assert "Envoyé à faycal@example.fr par host.docker.internal." in capsys.readouterr().out
        smtp.fail = True
        assert cli.main(["send-test-email", "faycal@example.fr"]) == 1
        assert "Échec" in capsys.readouterr().err
    finally:
        get_mailer.cache_clear()
