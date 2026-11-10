"""Schemas of the platform administration (``/admin``).

Supervision answers carry identities and counters only: no schema here has a field for the
text of a memoir, a DCE or a document, the title of a bid or a line of a company profile.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class SetupLookupIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class SetupLookupOut(BaseModel):
    email: str


class SetupPasswordIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=200)


class SetupPasswordOut(BaseModel):
    """Shown once, during the activation: the secret never leaves the server afterwards."""

    secret: str
    otpauth_uri: str
    qr_svg: str


class SetupConfirmIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=32)


class AdminMeOut(BaseModel):
    email: str
    full_name: str | None
    recovery_codes_left: int
    previous_login_at: datetime | None  # to spot a sign-in that was not yours


class SetupConfirmOut(BaseModel):
    recovery_codes: list[str]  # shown once
    me: AdminMeOut


class AdminLoginIn(BaseModel):
    # Plain strings on purpose: a malformed address gets the same refusal as a wrong one.
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=32)
