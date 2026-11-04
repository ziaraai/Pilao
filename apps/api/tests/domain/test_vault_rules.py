from datetime import date

import pytest

from app.domain.vault import add_months, derive_valid_until, effective_status, siren_matches

TODAY = date(2026, 11, 4)


@pytest.mark.parametrize(
    ("start", "months", "expected"),
    [
        (date(2026, 10, 15), 6, date(2027, 4, 15)),
        (date(2026, 8, 31), 6, date(2027, 2, 28)),  # end of month is clamped
        (date(2027, 8, 31), 6, date(2028, 2, 29)),  # leap year
        (date(2026, 11, 30), 3, date(2027, 2, 28)),
        (date(2026, 12, 15), 1, date(2027, 1, 15)),  # year rollover
    ],
)
def test_add_months(start: date, months: int, expected: date) -> None:
    assert add_months(start, months) == expected


def test_validity_derivation_rules() -> None:
    issued = date(2026, 10, 15)
    assert derive_valid_until("urssaf_vigilance", issued, None) == (
        date(2027, 4, 15),
        "urssaf_6_months",
    )
    assert derive_valid_until("kbis", issued, None) == (date(2027, 1, 15), "kbis_3_months")
    # a written end date always wins over a rule
    assert derive_valid_until("urssaf_vigilance", issued, date(2027, 1, 1)) == (
        date(2027, 1, 1),
        "written",
    )
    assert derive_valid_until("tax_compliance", issued, None) == (None, None)  # nothing to assume
    assert derive_valid_until("kbis", None, None) == (None, None)


@pytest.mark.parametrize(
    ("days", "status"),
    [
        (365, "valid"),
        (31, "valid"),
        (30, "expiring"),
        (1, "expiring"),
        (0, "expiring"),
        (-1, "expired"),
    ],
)
def test_status_thresholds(days: int, status: str) -> None:
    valid_until = date.fromordinal(TODAY.toordinal() + days)
    info = effective_status(confirmed=True, siren_ok=True, valid_until=valid_until, today=TODAY)
    assert (info.status, info.days_left) == (status, days)


def test_status_priority_and_edge_cases() -> None:
    far = date(2030, 1, 1)
    assert (
        effective_status(confirmed=False, siren_ok=True, valid_until=far, today=TODAY).status
        == "pending_review"
    )
    assert (
        effective_status(confirmed=False, siren_ok=False, valid_until=None, today=TODAY).status
        == "pending_review"
    )
    assert (
        effective_status(confirmed=True, siren_ok=False, valid_until=far, today=TODAY).status
        == "mismatch"
    )
    assert (
        effective_status(
            confirmed=True, siren_ok=False, valid_until=date(2020, 1, 1), today=TODAY
        ).status
        == "mismatch"
    )
    assert (
        effective_status(confirmed=True, siren_ok=True, valid_until=None, today=TODAY).status
        == "valid"
    )


def test_siren_matching() -> None:
    assert siren_matches(None, "123456789") and siren_matches("123456789", "123456789")
    assert not siren_matches("987654321", "123456789")
