"""The DCE e-mail address (24/11): what an e-mail sent or forwarded to ``dce+CODE@pilao.pro``
holds, whose company it is for, and which dossier it is about. Pure functions: no network."""

import html
import re
import secrets
import uuid
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr

from app.domain.dce import normalize

# no 0/o, 1/i/l: the code is read aloud and typed by hand
CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
CODE_LENGTH = 6
RECIPIENT_HEADERS = ("To", "Cc", "Delivered-To", "X-Original-To", "Envelope-To", "X-Forwarded-To")
_LINK = re.compile(r"https?://[^\s<>\"'\]]+", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_UPDATE_WORDS = (
    "avis de modification",
    "modification",
    "modifie",
    "rectificatif",
    "nouvelle version",
    "mise a jour",
)
_STOP = {"pour", "avec", "dans", "des", "les", "lot", "lots", "marche", "marches", "accord"}


@dataclass(frozen=True)
class Attachment:
    filename: str
    data: bytes


@dataclass
class ParsedMail:
    sender: str
    recipients: list[str]
    subject: str
    message_id: str | None
    text: str
    attachments: list[Attachment] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    auth_results: list[str] = field(default_factory=list)  # topmost first


@dataclass(frozen=True)
class DossierRef:
    id: uuid.UUID
    reference: str | None
    title: str
    buyer: str | None


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def code_from(addresses: list[str], local: str = "dce", domain: str = "pilao.pro") -> str | None:
    """The company's code in ``dce+CODE@domain`` among the recipients (any header value)."""
    wanted = re.compile(rf"^{re.escape(local)}\+([a-z0-9]{{4,12}})@{re.escape(domain.lower())}$")
    for _, address in getaddresses(addresses):
        found = wanted.match(address.strip().lower())
        if found:
            return found.group(1)
    return None


def _text_of(part: Message) -> str:
    try:
        content = part.get_content()  # type: ignore[attr-defined]
    except (KeyError, LookupError, ValueError):
        payload = part.get_payload(decode=True)
        content = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else ""
    return str(content)


def _walk(msg: Message, out: ParsedMail, texts: list[str], htmls: list[str]) -> None:
    for part in msg.iter_parts() if isinstance(msg, EmailMessage) else []:
        ctype = part.get_content_type()
        if ctype == "message/rfc822":  # an e-mail forwarded as an attachment
            for inner in part.iter_parts():
                if isinstance(inner, EmailMessage):
                    subject = str(inner.get("Subject") or "")
                    if subject:
                        texts.append(subject)
                    _walk_single(inner, out, texts, htmls)
            continue
        filename = part.get_filename()
        if part.get("Content-ID") and part.get_content_maintype() == "image":
            continue  # an image shown in the message (a signature's logo), not a piece
        if filename and not part.is_multipart():
            data = part.get_payload(decode=True)
            if isinstance(data, bytes) and data:
                out.attachments.append(Attachment(filename, data))
            continue
        if part.is_multipart():
            _walk(part, out, texts, htmls)
        elif ctype == "text/plain":
            texts.append(_text_of(part))
        elif ctype == "text/html":
            htmls.append(_text_of(part))


def _walk_single(msg: EmailMessage, out: ParsedMail, texts: list[str], htmls: list[str]) -> None:
    if msg.is_multipart():
        _walk(msg, out, texts, htmls)
    elif msg.get_content_type() == "text/html":
        htmls.append(_text_of(msg))
    else:
        texts.append(_text_of(msg))


def _links(*chunks: str) -> list[str]:
    seen: list[str] = []
    for chunk in chunks:
        for raw in _LINK.findall(html.unescape(chunk)):
            link = raw.rstrip(".,;:)!?")
            if link not in seen:
                seen.append(link)
    return seen


def parse(raw: bytes) -> ParsedMail:
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    assert isinstance(msg, EmailMessage)
    recipients = [str(v) for h in RECIPIENT_HEADERS for v in (msg.get_all(h) or [])]
    out = ParsedMail(
        sender=parseaddr(str(msg.get("From") or ""))[1].lower(),
        recipients=recipients,
        subject=str(msg.get("Subject") or "").strip(),
        message_id=(str(msg.get("Message-ID")).strip() or None) if msg.get("Message-ID") else None,
        text="",
        auth_results=[str(v) for v in (msg.get_all("Authentication-Results") or [])],
    )
    texts: list[str] = []
    htmls: list[str] = []
    _walk_single(msg, out, texts, htmls)
    plain = "\n".join(t for t in texts if t.strip())
    if not plain.strip() and htmls:
        plain = "\n".join(html.unescape(_TAG.sub(" ", h)) for h in htmls)
    out.text = plain.strip()
    out.links = _links(*texts, *htmls)
    return out


_PASS = re.compile(
    r"\b(dmarc=pass\b[^;]*?header\.from=(?P<a>[^\s;]+)"
    r"|dkim=pass\b[^;]*?header\.(?:d|i)=@?(?P<b>[^\s;]+)"
    r"|spf=pass\b[^;]*?smtp\.mailfrom=(?:[^\s;@]*@)?(?P<c>[^\s;]+))",
    re.IGNORECASE,
)


def authenticated(sender: str, auth_results: list[str], server: str | None = None) -> bool:
    """The sender's domain was checked by our own mail server (DMARC, DKIM or SPF passed for
    that very domain). Only the topmost Authentication-Results header counts: it is the one
    the receiving server added; the ones below came with the e-mail and may be forged. With
    ``server``, that header must also carry our server's name."""
    if not auth_results or "@" not in sender:
        return False
    top = auth_results[0]
    if server and top.split(";", 1)[0].strip().lower() != server.lower():
        return False
    domain = sender.rsplit("@", 1)[1].lower()
    for found in _PASS.finditer(top):
        checked = (found.group("a") or found.group("b") or found.group("c") or "").lower()
        if checked.strip(">\"'") == domain:
            return True
    return False


_REPLY = re.compile(r"^\s*(?:(?:tr|fw|fwd|re|ref|réf)\s*:\s*)+", re.IGNORECASE)
_BOILERPLATE = re.compile(
    r"^\s*(?:mise à disposition (?:du|d'un) dce|dossier de consultation(?: des entreprises)?"
    r"|dce)\s*[-–:]\s*",
    re.IGNORECASE,
)
UNTITLED = "Dossier reçu par e-mail"


def title_from_subject(subject: str) -> str:
    """A dossier opened from an e-mail is named after its subject, without « TR: » and the
    platform's boilerplate."""
    title = _REPLY.sub("", subject)
    title = _BOILERPLATE.sub("", title).strip(" -–:")
    return (title or UNTITLED)[:200]


def is_update_notice(subject: str, text: str) -> bool:
    """A platform's notice that the DCE changed (no attachment: the link to fetch it)."""
    words = normalize(f"{subject} {text}")
    return any(w in words for w in _UPDATE_WORDS)


def _compact(text: str) -> str:
    return normalize(text).replace(" ", "")


def _significant(text: str) -> set[str]:
    return {w for w in normalize(text).split() if len(w) >= 4 and w not in _STOP}


def match_dossier(subject: str, text: str, dossiers: list[DossierRef]) -> uuid.UUID | None:
    """The dossier the e-mail is about: its reference (5 characters or more, dashes and spaces
    ignored), else every significant word of its title (3 at least). Never a guess between
    two dossiers."""
    whole = f"{subject}\n{text}"
    compact = _compact(whole)
    by_ref = {
        d.id
        for d in dossiers
        if d.reference and len(_compact(d.reference)) >= 5 and _compact(d.reference) in compact
    }
    if by_ref:
        return next(iter(by_ref)) if len(by_ref) == 1 else None
    words = _significant(whole)
    by_title = [
        d.id for d in dossiers if len(_significant(d.title)) >= 3 and _significant(d.title) <= words
    ]
    return by_title[0] if len(by_title) == 1 else None
