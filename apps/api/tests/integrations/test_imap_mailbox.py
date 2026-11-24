"""The DCE mailbox's IMAP client (ADR-055), against a fake server speaking imaplib's replies."""

import imaplib
import ssl
from typing import Any

import pytest

from app.integrations.imap_mailbox import ImapMailbox, MailboxError, Waiting


class FakeImap:
    def __init__(self, password: str = "ok") -> None:
        self.password = password
        self.calls: list[tuple[Any, ...]] = []
        self.sock = None

    def login(self, user: str, password: str) -> tuple[str, list[bytes]]:
        self.calls.append(("login", user))
        if password != self.password:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Authentication failed.")
        return "OK", [b"Logged in"]

    def select(self, box: str) -> tuple[str, list[bytes]]:
        return "OK", [b"3"]

    def uid(self, command: str, *args: str) -> tuple[str, list[Any]]:
        self.calls.append((command, *args))
        if command == "SEARCH" and args == ("UNDELETED",):
            return "OK", [b"7 8 9"]
        if command == "SEARCH":
            return "OK", [b"8"]
        if command == "FETCH" and args[1] == "(RFC822.SIZE)":
            return "OK", [
                b"1 (UID 7 RFC822.SIZE 1200)",
                b"2 (RFC822.SIZE 99999999 UID 8)",
                b"3 (UID 9 RFC822.SIZE 50)",
            ]
        if command == "FETCH":
            return "OK", [(b"1 (UID 7 BODY[] {5}", b"hello"), b")"]
        return "OK", [b""]

    def expunge(self) -> tuple[str, list[bytes]]:
        self.calls.append(("EXPUNGE",))
        return "OK", []

    def close(self) -> None:
        self.calls.append(("CLOSE",))

    def logout(self) -> None:
        self.calls.append(("LOGOUT",))

    def shutdown(self) -> None:
        self.calls.append(("SHUTDOWN",))


def open_with(fake: FakeImap, password: str = "ok", **kw: Any) -> ImapMailbox:
    def connect(host: str, port: int, context: ssl.SSLContext, timeout: int) -> FakeImap:
        fake.calls.append(("connect", host, port, context.verify_mode))
        return fake

    return ImapMailbox("pilao.pro", 993, "dce@pilao.pro", password, connect=connect, **kw)  # type: ignore[arg-type]


def test_lists_fetches_flags_and_deletes() -> None:
    fake = FakeImap()
    box = open_with(fake)
    assert box.waiting() == [
        Waiting("7", 1200, False),
        Waiting("8", 99999999, True),
        Waiting("9", 50, False),
    ]
    assert box.fetch("7") == b"hello"
    assert ("FETCH", "7", "(BODY.PEEK[])") in fake.calls  # never marked read by a fetch
    box.flag("8")
    box.delete("7")
    box.close()
    assert ("STORE", "8", "+FLAGS", "(\\Flagged)") in fake.calls
    assert ("STORE", "7", "+FLAGS", "(\\Deleted)") in fake.calls
    assert fake.calls[-3:] == [("EXPUNGE",), ("CLOSE",), ("LOGOUT",)]


def test_a_wrong_password_says_so() -> None:
    with pytest.raises(MailboxError, match="mot de passe incorrect"):
        open_with(FakeImap(), password="faux")


def test_an_unreachable_server_says_so() -> None:
    def refuse(*_: Any) -> FakeImap:
        raise ConnectionRefusedError

    with pytest.raises(MailboxError, match="injoignable"):
        ImapMailbox("pilao.pro", 993, "dce@pilao.pro", "ok", connect=refuse)


def test_the_local_hop_does_not_check_the_certificate() -> None:
    fake = FakeImap()
    open_with(fake, verify_tls=False)
    assert fake.calls[0][3] == ssl.CERT_NONE
    fake = FakeImap()
    open_with(fake)
    assert fake.calls[0][3] == ssl.CERT_REQUIRED
