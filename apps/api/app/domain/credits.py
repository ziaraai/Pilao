"""Credits arithmetic (lot 4, ADR-043): the balance comes from the ledger, nothing is written
on the 1st of the month.

A company has its plan's monthly allowance, renewed every calendar month (Paris time), and
extra credits (top-ups, welcome credits) that never expire. A charge takes the month's credits
first, then the extra ones. Entries are signed: a charge is negative, the rest positive.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def paris_month(at: datetime) -> date:
    """The first day of the Paris calendar month of ``at``."""
    local = at.astimezone(PARIS)
    return date(local.year, local.month, 1)


def _next_month(month: date) -> date:
    return date(month.year + 1, 1, 1) if month.month == 12 else date(month.year, month.month + 1, 1)


@dataclass(frozen=True)
class Ledger:
    """One ledger line, as the arithmetic sees it. ``month``: the Paris month of a charge (and
    of a refund of a charge of the same month); ``None`` for what is not tied to a month."""

    monthly: int
    extra: int
    month: date | None


@dataclass(frozen=True)
class Balance:
    monthly_allowance: int
    monthly_left: int
    extra: int
    total: int
    reference: int  # what the low-credits banner compares with
    renews_on: date


class InsufficientCredits(Exception):
    def __init__(self, needed: int, left: int) -> None:
        super().__init__(f"{needed} needed, {left} left")
        self.needed, self.left = needed, left


def compute_balance(
    monthly_allowance: int, welcome_credits: int, entries: Iterable[Ledger], now: datetime
) -> Balance:
    month = paris_month(now)
    used = 0
    extra = 0
    for e in entries:
        if e.month == month:
            used -= e.monthly
        extra += e.extra
    monthly_left = max(0, monthly_allowance - used)
    extra = max(0, extra)
    return Balance(
        monthly_allowance=monthly_allowance,
        monthly_left=monthly_left,
        extra=extra,
        total=monthly_left + extra,
        reference=monthly_allowance if monthly_allowance > 0 else welcome_credits,
        renews_on=_next_month(month),
    )


def split_charge(balance: Balance, cost: int) -> tuple[int, int]:
    """How much of ``cost`` comes from the month's credits and how much from the extra ones."""
    if cost > balance.total:
        raise InsufficientCredits(cost, balance.total)
    from_month = min(cost, balance.monthly_left)
    return from_month, cost - from_month


def refund_parts(
    monthly: int, extra: int, month: date, now: datetime
) -> tuple[int, int, date | None]:
    """What a refund writes back for a charge of ``monthly``/``extra`` (negative) taken in
    ``month``: the same parts in the same month; once that month is over, its part of the
    month comes back as extra credits (nothing is lost)."""
    if paris_month(now) == month:
        return -monthly, -extra, month
    return 0, -(monthly + extra), None
