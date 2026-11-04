"""E-mail sending behind a small interface. Real SMTP provider comes later (ADR to add)."""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

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


@lru_cache
def get_mailer() -> Mailer:
    return ConsoleMailer()
