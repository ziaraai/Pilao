"""The minimum and maximum of an accord-cadre (« Montant minimum annuel 80 000 € HT… »).

Many DCEs give no estimated amount but bound the accord-cadre instead. The analysis now asks
the model for them (``key_info.framework_amounts``); an analysis made before that is read from
the texts it already holds (duration, procedure), so a dossier needs no new (paid) analysis.
Pure functions: no database, no network.
"""

import re
from dataclasses import dataclass
from typing import Any

_KEYWORD = r"\b(minimum|maximum|minimal|maximal|mini|maxi)\b"
_NUMBER = r"(\d{1,3}(?:[ \u00a0\u202f.]\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)"
_AMOUNT = re.compile(
    _KEYWORD + r"(?:(?!\b(?:mini|maxi))[^0-9€;\n]){0,40}?" + _NUMBER + r"\s*(k€|m€|€|euros?)",
    re.IGNORECASE,
)
_PER_YEAR = re.compile(r"\bannuel(?:le)?s?\b|\bpar an\b|/\s*an\b|\bannuellement\b", re.IGNORECASE)
_WHOLE = re.compile(
    r"\bdurée (?:totale|globale)\b|\btoute la durée\b|\bsur la durée\b|\bpour la durée\b",
    re.IGNORECASE,
)
_FACTOR = {"€": 1, "euro": 1, "euros": 1, "k€": 1_000, "m€": 1_000_000}


@dataclass(frozen=True)
class FrameworkAmounts:
    minimum_cents: int | None
    maximum_cents: int | None
    per_year: bool | None  # None: the DCE does not say
    source: dict[str, Any] | None


def _cents(number: str, unit: str) -> int:
    whole, _, decimals = re.sub(r"[ \u00a0\u202f.]", "", number).partition(",")
    euros = int(whole) + (int(decimals.ljust(2, "0")) / 100 if decimals else 0)
    return round(euros * _FACTOR[unit.lower()] * 100)


def parse(text: str | None) -> tuple[int | None, int | None, bool | None] | None:
    """(minimum, maximum, per year) in cents, or ``None`` when the text bounds no amount."""
    if not text:
        return None
    found: dict[str, int] = {}
    for m in _AMOUNT.finditer(text):
        kind = "min" if m.group(1).lower().startswith("mini") else "max"
        found.setdefault(kind, _cents(m.group(2), m.group(3)))
    low, high = found.get("min"), found.get("max")
    if low is None and high is None:
        return None
    if low is not None and high is not None and low > high:
        return None  # read wrongly or written wrongly: better nothing than a wrong range
    per_year = True if _PER_YEAR.search(text) else (False if _WHOLE.search(text) else None)
    return low, high, per_year


def _to_cents(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return None
    return round(value * 100)


def from_analysis(data: dict[str, Any]) -> FrameworkAmounts | None:
    key_info = data.get("key_info") or {}
    field = key_info.get("framework_amounts") or {}
    low, high = _to_cents(field.get("minimum_eur_ht")), _to_cents(field.get("maximum_eur_ht"))
    if low is not None or high is not None:
        per_year = {"year": True, "contract": False}.get(str(field.get("period")))
        return FrameworkAmounts(low, high, per_year, field.get("source"))
    for key in ("duration", "procedure"):  # an analysis made before the field existed
        item = key_info.get(key) or {}
        parsed = parse(item.get("value") if isinstance(item.get("value"), str) else None)
        if parsed:
            return FrameworkAmounts(*parsed, item.get("source"))
    return None


def _euros(cents: int) -> str:
    return f"{cents / 100:,.0f} €".replace(",", " ")


def describe(a: FrameworkAmounts, standalone: bool = False) -> str:
    """« de 80 000 € à 170 000 € HT par an » — or, alone on a line, « De 80 000 €… »."""
    if a.minimum_cents is not None and a.maximum_cents is not None:
        phrase = f"de {_euros(a.minimum_cents)} à {_euros(a.maximum_cents)} HT"
    elif a.maximum_cents is not None:
        phrase = f"jusqu'à {_euros(a.maximum_cents)} HT"
    else:
        phrase = f"{'au' if standalone else "d'au"} moins {_euros(a.minimum_cents or 0)} HT"
    phrase += {True: " par an", False: " sur toute la durée", None: ""}[a.per_year]
    return phrase[0].upper() + phrase[1:] if standalone else phrase
