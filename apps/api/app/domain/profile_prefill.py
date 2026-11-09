"""Pre-filling the profile from the company's documents: checks applied to what the model
read (spec 2026-11-09, §5). Pure rules: no database, no model.

A proposed line is kept only if its sentence is found in the document (``locate``) and its
name is written in that sentence; a number (headcount, quantity, amount, year) is kept only if
it is written there too, otherwise the field is left to fill in. People's names are dropped:
a team is a role and a headcount. ``dedupe`` removes what the profile already has.
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.dce import normalize

KINDS = ("human_resource", "equipment", "certification", "reference")
# The first field is the line's name; the others must be filled before it joins the profile.
REQUIRED: dict[str, tuple[str, ...]] = {
    "human_resource": ("qualification", "count"),
    "equipment": ("name",),
    "certification": ("name",),
    "reference": ("client_name", "client_type", "title"),
}

_QUOTES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "«": " ", "»": " "})
_THOUSANDS = re.compile(r"(?<=\d)[  .](?=\d{3}(?!\d))")
_PERSON = re.compile(r"\b(?:M\.?|Mme|Mlle|Monsieur|Madame)\s+[A-ZÀ-Ý].*$")
_DEPARTMENT = re.compile(r"^(?:\d{2,3}|2A|2B)$")


@dataclass(frozen=True)
class Passage:
    content: str
    page: int | None
    heading: str | None


@dataclass(frozen=True)
class Located:
    page: int | None
    heading: str | None


@dataclass(frozen=True)
class Clean:
    kind: str
    data: dict[str, Any]
    missing: list[str]
    key: str


def _norm(text: str) -> str:
    return normalize(text.translate(_QUOTES))


def locate(excerpt: str, passages: list[Passage]) -> Located | None:
    """The passage that holds ``excerpt`` (typography aside); across passages, no page."""
    wanted = _norm(excerpt)
    if not wanted:
        return None
    for p in passages:
        if wanted in _norm(p.content):
            return Located(p.page, p.heading)
    if wanted in _norm(" ".join(p.content for p in passages)):
        return Located(None, None)
    return None


def numbers_in(text: str) -> set[int]:
    """The whole numbers written in ``text``, thousands separators removed."""
    return {int(n) for n in re.findall(r"\d+", _THOUSANDS.sub("", text))}


def _text(value: Any, limit: int = 300) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None


def _stem(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") else token


def _written(value: str | None, excerpt_norm: str) -> bool:
    """At least one significant word of ``value`` is in the (normalized) excerpt."""
    if not value:
        return False
    tokens = _norm(value).split()
    words = [t for t in tokens if len(t) >= 4] or tokens
    return any(_stem(t) in excerpt_norm for t in words)


def _int(value: Any, low: int, high: int, written: set[int]) -> int | None:
    try:
        number = round(float(str(value).replace(",", ".").replace(" ", "")))
    except (TypeError, ValueError, OverflowError):
        return None
    return number if low <= number <= high and number in written else None


def _client_type(value: Any) -> str | None:
    text = _norm(str(value or ""))
    if text == "public":
        return "public"
    if text in ("prive", "private"):
        return "private"
    return None


def _date(value: Any, written: set[int]) -> str | None:
    try:
        day = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return day.isoformat() if day.year in written else None


def _without_person(text: str | None) -> str | None:
    if text is None:
        return None
    return _PERSON.sub("", text).strip(" -,;:") or None


def clean(kind: str, raw: dict[str, Any], excerpt: str) -> Clean | None:
    """The line as it may be proposed, or ``None`` if its name is missing or not in the
    excerpt. Unsourced or out-of-range values become ``None``."""
    seen = _norm(excerpt)
    nums = numbers_in(excerpt)
    data: dict[str, Any]
    if kind == "human_resource":
        description = _text(raw.get("description"), 5000)
        data = {
            "qualification": _without_person(_text(raw.get("qualification"))),
            "count": _int(raw.get("count"), 0, 100_000, nums),
            "description": None if description and _PERSON.search(description) else description,
        }
    elif kind == "equipment":
        data = {
            "name": _text(raw.get("name")),
            "category": _text(raw.get("category")),
            "quantity": _int(raw.get("quantity"), 0, 1_000_000, nums),
        }
    elif kind == "certification":
        number = _text(raw.get("number"))
        data = {
            "name": _text(raw.get("name")),
            "number": number if number and _norm(number) in seen else None,
            "valid_until": _date(raw.get("valid_until"), nums),
        }
    elif kind == "reference":
        title, location = _text(raw.get("title")), _text(raw.get("location"))
        department = _text(raw.get("department"), 3)
        euros = _int(raw.get("amount_eur"), 1, 10**10, nums)
        data = {
            "client_name": _text(raw.get("client_name")),
            "client_type": _client_type(raw.get("client_type")),
            "title": title if _written(title, seen) else None,
            "location": location if _written(location, seen) else None,
            "department": (
                department
                if department and _DEPARTMENT.match(department) and _norm(department) in seen
                else None
            ),
            "amount_cents": euros * 100 if euros is not None else None,
            "year": _int(raw.get("year"), 1950, 2100, nums),
            "duration_months": _int(raw.get("duration_months"), 0, 1200, nums),
            "description": _text(raw.get("description"), 5000),
        }
    else:
        raise ValueError(f"unknown kind: {kind}")
    name, *required = REQUIRED[kind]
    if not _written(data[name], seen):
        return None
    missing = [f for f in required if data[f] is None]
    return Clean(kind, data, missing, key_of(kind, data))


def _key(text: Any) -> str:
    return " ".join(_stem(t) for t in _norm(str(text or "")).split())


def key_of(kind: str, data: dict[str, Any]) -> str:
    """What two lines of the same kind share when they are the same thing."""
    if kind == "reference":
        return f"{_key(data.get('client_name'))}|{_key(data.get('title'))}"
    return _key(data.get(REQUIRED[kind][0]))


def dedupe(items: list[Clean], known: set[str]) -> list[Clean]:
    """Drop the lines already known (profile, handled proposals) and repeats; a reference
    without its subject is dropped when its client is already known."""
    clients = {k.split("|", 1)[0] for k in known if "|" in k}
    seen: set[str] = set()
    kept: list[Clean] = []
    for item in items:
        if item.key in known or item.key in seen:
            continue
        if item.kind == "reference":
            client, title = item.key.split("|", 1)
            if not title and client in clients:
                continue
            clients.add(client)
        seen.add(item.key)
        kept.append(item)
    return kept
