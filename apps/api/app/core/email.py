"""E-mail sending behind a small interface (ADR-032).

* ``SmtpMailer`` as soon as ``SMTP_HOST`` is set: any SMTP server (the Plesk mail server
  of the pilot, Brevo, Scaleway TEM…), STARTTLS by default, certificate verified.
* ``ConsoleMailer`` otherwise, outside production only: it logs the message.
* in production without SMTP, sending is refused (fail closed: the console would log
  one-shot links in clear and deliver nothing).
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.core.errors import ApiError

logger = logging.getLogger("pilao.email")


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    def send(self, message: Email) -> None: ...


class ConsoleMailer:
    """Local default: logs the message (never used in production)."""

    def send(self, message: Email) -> None:
        logger.info("EMAIL to=%s subject=%s\n%s", message.to, message.subject, message.body)


class SmtpMailer:
    """Plain-text e-mails through an SMTP server; one connection per message (low volume)."""

    def __init__(
        self,
        host: str,
        port: int,
        sender: str,
        user: str = "",
        password: str = "",
        starttls: bool = True,
        verify_tls: bool = True,
        timeout: float = 20.0,
    ) -> None:
        self._host, self._port, self._sender = host, port, sender
        self._user, self._password, self._starttls, self._timeout = (
            user,
            password,
            starttls,
            timeout,
        )
        self._context = ssl.create_default_context()
        if not verify_tls:  # only for the server's own mail system: the hop stays local
            self._context.check_hostname = False
            self._context.verify_mode = ssl.CERT_NONE

    def send(self, message: Email) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self._sender, message.to, message.subject
        msg["Date"] = formatdate(localtime=False)
        msg["Message-ID"] = make_msgid(domain=self._sender.rsplit("@", 1)[-1].strip("> "))
        msg.set_content(message.body)  # UTF-8, French accents included
        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                if self._starttls:
                    smtp.starttls(context=self._context)
                if self._user:
                    smtp.login(self._user, self._password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            logger.exception("e-mail to %s not sent", message.to)
            raise ApiError(
                503, "email_unavailable", "L'e-mail n'a pas pu être envoyé : réessayez."
            ) from exc


def send_quietly(mailer: Mailer, message: Email) -> bool:
    """For automatic messages (alerts, notices): a failure is logged, never raised, so one
    unreachable mail server cannot stop the hourly run for everyone."""
    try:
        mailer.send(message)
        return True
    except Exception:
        logger.exception("automatic e-mail to %s not sent", message.to)
        return False


@lru_cache
def get_mailer() -> Mailer:
    s = get_settings()
    if s.smtp_host:
        return SmtpMailer(
            s.smtp_host,
            s.smtp_port,
            s.smtp_from,
            s.smtp_user,
            s.smtp_password,
            s.smtp_starttls,
            s.smtp_verify_tls,
        )
    if s.environment == "production":
        raise ApiError(503, "email_unavailable", "L'envoi d'e-mails n'est pas encore configuré.")
    return ConsoleMailer()
