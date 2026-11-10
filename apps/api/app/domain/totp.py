"""Authenticator codes (TOTP, RFC 6238: SHA-1, 6 digits, 30 s) and recovery codes.

Pure rules: the caller keeps the last accepted step, so that a code is never used twice.
"""

import hmac
import io
import secrets
from datetime import datetime

import pyotp
import segno

PURPOSE = "pilao/platform-admin/totp"  # encryption purpose of the stored secret (core.crypto)
ISSUER = "Pilao Administration"
STEP = 30
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no i, l, o, 0, 1: codes are copied by hand


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def qr_svg(uri: str) -> str:
    out = io.BytesIO()
    segno.make(uri, error="m").save(out, kind="svg", scale=5, border=2, xmldecl=False)
    return out.getvalue().decode()


def step_at(when: datetime) -> int:
    return int(when.timestamp()) // STEP


def matching_step(secret: str, code: str, when: datetime) -> int | None:
    """The time step (previous, current or next) whose code is ``code``, if any."""
    digits = "".join(code.split())
    if len(digits) != 6 or not digits.isdigit():
        return None
    totp, current = pyotp.TOTP(secret), step_at(when)
    found = None
    for step in (current - 1, current, current + 1):
        if hmac.compare_digest(totp.at(step * STEP), digits):
            found = step
    return found


def new_recovery_codes(n: int = 8) -> list[str]:
    def part() -> str:
        return "".join(secrets.choice(_ALPHABET) for _ in range(5))

    return [f"{part()}-{part()}" for _ in range(n)]


def normalize_recovery(code: str) -> str:
    """As typed by hand: any case, spaces, with or without the dash."""
    text = "".join(code.split()).lower().replace("-", "")
    return f"{text[:5]}-{text[5:]}" if len(text) > 5 else text
