"""The DCE mailbox read over IMAP (ADR-055): list, fetch, flag, delete. Nothing else is done
with the e-mails here: ``services/inbound_mail.py`` reads them."""

import imaplib
import re
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.core import runtime
from app.core.config import get_settings
from app.platform_settings import DCE_MAIL_PASSWORD

TIMEOUT_SECONDS = 60
_SIZE = re.compile(rb"UID (\d+) RFC822\.SIZE (\d+)|RFC822\.SIZE (\d+) UID (\d+)")


class MailboxError(Exception):
    """The mailbox cannot be read; the message says why, in French."""


@dataclass(frozen=True)
class Waiting:
    uid: str
    size: int
    flagged: bool


class Mailbox(Protocol):
    def waiting(self) -> list[Waiting]: ...
    def fetch(self, uid: str) -> bytes: ...
    def fetch_header(self, uid: str) -> bytes: ...
    def flag(self, uid: str) -> None: ...
    def delete(self, uid: str) -> None: ...
    def close(self) -> None: ...


Connect = Callable[[str, int, ssl.SSLContext, int], imaplib.IMAP4]


def _connect(host: str, port: int, context: ssl.SSLContext, timeout: int) -> imaplib.IMAP4:
    return imaplib.IMAP4_SSL(host, port, ssl_context=context, timeout=timeout)


class ImapMailbox:
    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        *,
        verify_tls: bool = True,
        tls_name: str = "",
        connect: Connect = _connect,
    ) -> None:
        context = ssl.create_default_context()
        if not verify_tls:  # the server's own mail system, reached on the local hop
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        elif tls_name:
            context.check_hostname = False  # checked below against the expected name
        self._tls_name = tls_name if verify_tls else ""
        try:
            self._imap = connect(host, port, context, TIMEOUT_SECONDS)
        except (OSError, imaplib.IMAP4.error) as exc:
            raise MailboxError(f"Serveur de messagerie injoignable ({host}:{port}).") from exc
        if self._tls_name:
            sock = getattr(self._imap, "sock", None)
            cert = sock.getpeercert() if isinstance(sock, ssl.SSLSocket) else None
            pairs = (cert or {}).get("subjectAltName", ())
            names = [str(p[1]) for p in pairs if isinstance(p, tuple) and p[0] == "DNS"]
            if self._tls_name not in names:
                self._imap.shutdown()
                raise MailboxError(f"Le certificat du serveur n'est pas celui de {tls_name}.")
        try:
            self._imap.login(user, password)
        except imaplib.IMAP4.error as exc:
            self._imap.shutdown()
            raise MailboxError("Connexion refusée : adresse ou mot de passe incorrect.") from exc
        status, _ = self._imap.select("INBOX")
        if status != "OK":
            self._imap.logout()
            raise MailboxError("La boîte de réception ne s'ouvre pas.")

    def waiting(self) -> list[Waiting]:
        status, data = self._imap.uid("SEARCH", "UNDELETED")
        if status != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        flagged = set(self._search("FLAGGED UNDELETED"))
        out = []
        for chunk in range(0, len(uids), 200):
            ids = b",".join(uids[chunk : chunk + 200]).decode()
            status, rows = self._imap.uid("FETCH", ids, "(RFC822.SIZE)")
            for row in rows if status == "OK" else []:
                line = row[0] if isinstance(row, tuple) else row
                found = _SIZE.search(line) if isinstance(line, bytes) else None
                if found:
                    uid = (found.group(1) or found.group(4)).decode()
                    size = int(found.group(2) or found.group(3))
                    out.append(Waiting(uid, size, uid in flagged))
        return out

    def _search(self, criteria: str) -> list[str]:
        status, data = self._imap.uid("SEARCH", *criteria.split())
        if status != "OK" or not data or not data[0]:
            return []
        return [u.decode() for u in data[0].split()]

    def _fetch(self, uid: str, part: str) -> bytes:
        status, data = self._imap.uid("FETCH", uid, f"({part})")
        for row in data if status == "OK" else []:
            if isinstance(row, tuple) and isinstance(row[1], bytes):
                return row[1]
        raise MailboxError(f"Message {uid} illisible.")

    def fetch(self, uid: str) -> bytes:
        return self._fetch(uid, "BODY.PEEK[]")

    def fetch_header(self, uid: str) -> bytes:
        return self._fetch(uid, "BODY.PEEK[HEADER]")

    def flag(self, uid: str) -> None:
        self._imap.uid("STORE", uid, "+FLAGS", "(\\Flagged)")

    def delete(self, uid: str) -> None:
        self._imap.uid("STORE", uid, "+FLAGS", "(\\Deleted)")

    def close(self) -> None:
        try:
            self._imap.expunge()
            self._imap.close()
            self._imap.logout()
        except (OSError, imaplib.IMAP4.error):
            pass


def open_mailbox(password: str | None = None) -> ImapMailbox:
    """The DCE mailbox with the settings in use (``password``: one being tried)."""
    s = get_settings()
    address = s.dce_mail_address
    secret = password if password is not None else runtime.secret(DCE_MAIL_PASSWORD)
    if not secret:
        raise MailboxError("Le mot de passe de la boîte n'est pas enregistré.")
    host = s.dce_mail_imap_host or address.partition("@")[2]
    return ImapMailbox(
        host,
        s.dce_mail_imap_port,
        address,
        secret,
        verify_tls=s.dce_mail_verify_tls,
        tls_name=s.dce_mail_tls_name,
    )


Opener = Callable[..., Mailbox]


def get_mailbox_opener() -> Opener:
    """FastAPI dependency (the administration's « Tester la connexion »); tests replace it."""
    return open_mailbox
