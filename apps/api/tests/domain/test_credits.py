"""Lot 4: the credits arithmetic (spec §2, §3.3). Pure: no database."""

from datetime import UTC, date, datetime

import pytest

from app.domain.credits import (
    InsufficientCredits,
    Ledger,
    compute_balance,
    paris_month,
    refund_parts,
    split_charge,
)

NOV = datetime(2026, 11, 15, 10, tzinfo=UTC)


def charge(monthly: int, extra: int, at: datetime = NOV) -> Ledger:
    return Ledger(monthly=-monthly, extra=-extra, month=paris_month(at))


def test_month_first_then_extra() -> None:
    granted = [Ledger(monthly=0, extra=5, month=None)]
    before = compute_balance(10, 0, granted, NOV)
    assert (before.monthly_left, before.extra, before.total) == (10, 5, 15)
    assert split_charge(before, 12) == (10, 2)

    after = compute_balance(10, 0, [*granted, charge(10, 2)], NOV)
    assert (after.monthly_left, after.extra, after.total) == (0, 3, 3)


def test_new_month_starts_again() -> None:
    october = charge(10, 0, datetime(2026, 10, 20, tzinfo=UTC))
    assert compute_balance(10, 0, [october], NOV).monthly_left == 10


def test_paris_month_boundary() -> None:
    late = datetime(2026, 11, 30, 23, 30, tzinfo=UTC)  # 1 December, 00:30 in Paris
    assert paris_month(late) == date(2026, 12, 1)
    assert compute_balance(10, 0, [charge(4, 0, late)], late).monthly_left == 6
    assert compute_balance(10, 0, [], NOV).renews_on == date(2026, 12, 1)


def test_smaller_allowance_never_negative() -> None:
    assert compute_balance(20, 0, [charge(30, 0)], NOV).monthly_left == 0


def test_refund_same_month() -> None:
    assert refund_parts(-3, -2, paris_month(NOV), NOV) == (3, 2, paris_month(NOV))


def test_refund_after_month_end() -> None:
    """Taken on 30 November, failed on 1 December: nothing is lost."""
    taken = datetime(2026, 11, 30, 12, tzinfo=UTC)
    failed = datetime(2026, 12, 1, 9, tzinfo=UTC)
    assert refund_parts(-3, -2, paris_month(taken), failed) == (0, 5, None)


def test_insufficient() -> None:
    balance = compute_balance(0, 0, [Ledger(monthly=0, extra=3, month=None)], NOV)
    with pytest.raises(InsufficientCredits) as caught:
        split_charge(balance, 5)
    assert (caught.value.needed, caught.value.left) == (5, 3)
    assert split_charge(balance, 0) == (0, 0)


def test_reference() -> None:
    assert compute_balance(0, 7, [], NOV).reference == 7
    assert compute_balance(100, 0, [], NOV).reference == 100
