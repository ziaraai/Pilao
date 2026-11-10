"""Authenticator codes (RFC 6238) and recovery codes of the platform administrators."""

import re
from datetime import UTC, datetime

import pyotp
import pytest

from app.domain import totp

# RFC 6238, appendix B (SHA-1): the ASCII secret « 12345678901234567890 », in base32.
SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def at(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, UTC)


@pytest.mark.parametrize(
    ("ts", "code"), [(59, "287082"), (1111111109, "081804"), (1234567890, "005924")]
)
def test_rfc_vectors(ts: int, code: str) -> None:
    assert totp.matching_step(SECRET, code, at(ts)) == ts // 30


def test_neighbour_steps_only() -> None:
    code_step_2, code_step_3 = pyotp.TOTP(SECRET).at(60), pyotp.TOTP(SECRET).at(90)
    assert totp.matching_step(SECRET, code_step_2, at(59)) == 2  # the next step is accepted
    assert totp.matching_step(SECRET, code_step_3, at(59)) is None  # two steps away is not


def test_typed_code_is_tolerated_but_not_garbage() -> None:
    assert totp.matching_step(SECRET, " 287 082 ", at(59)) == 1
    for bad in ("", "28708", "2870820", "abcdef"):
        assert totp.matching_step(SECRET, bad, at(59)) is None


def test_recovery_codes() -> None:
    codes = totp.new_recovery_codes()
    assert len(codes) == len(set(codes)) == 8
    assert all(re.fullmatch(r"[a-hjkmnp-z2-9]{5}-[a-hjkmnp-z2-9]{5}", c) for c in codes)
    assert totp.normalize_recovery(" ABCDE fghjk ") == "abcde-fghjk"
    assert totp.normalize_recovery("abcde-fghjk") == "abcde-fghjk"


def test_qr_and_uri() -> None:
    uri = totp.provisioning_uri(SECRET, "a@b.fr")
    assert uri.startswith("otpauth://totp/")
    assert f"secret={SECRET}" in uri and "issuer=Pilao" in uri
    assert totp.qr_svg(uri).lstrip().startswith("<svg")


def test_secrets_differ() -> None:
    assert totp.new_secret() != totp.new_secret()
    assert totp.step_at(at(59)) == 1
